"""Teil B routes: course overview, invitation links, groups, people, hand-over and providers.

Thin layer over ``services/learning/verwaltung.py``, which holds every rights and
protection rule. Mounted only in the local learning mode; every route also answers 404
once the mode is off. ``Verweigert`` becomes 403 ``{detail}``, ``LinkUngueltig`` 410
``{detail, grund}``. Tokens, e-mail addresses and keys never appear in a log line or an
answer; the only exception is the URL with a freshly created token, returned once to its
creator.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.events.database import get_db_session
from src.core.learning_mode import is_local_learning_mode_enabled
from src.db.courses.courses import Course
from src.db.organizations import Organization, OrganizationCreate
from src.db.user_organizations import UserOrganization
from src.db.users import AnonymousUser, PublicUser, User, UserCreate
from src.routers.auth import set_auth_cookies
from src.routers.learning.bootstrap import require_local_learning_bootstrap
from src.security.auth import get_authenticated_user
from src.security.session_context import AUTH_METHOD_PASSWORD
from src.services.auth.session import issue_session_or_challenge
from src.services.learning import verwaltung as dienst
from src.services.learning.personen import KennungVergeben, actor_von
from src.services.learning.uebergabe import uebergabe_token
from src.services.orgs.auth_policy import enforce_login_auth_method
from src.services.orgs.orgs import create_org
from src.services.security.rate_limiting import check_invite_acceptance_rate_limit
from src.services.users.users import create_user

HUELLE_BASIS_ENV = "LEARNHOUSE_LEARNING_HUELLE_BASIS"
WEB_BASIS_ENV = "LEARNHOUSE_LEARNING_WEB_BASIS"


def _nur_im_lernmodus() -> None:
    if not is_local_learning_mode_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


router = APIRouter(dependencies=[Depends(_nur_im_lernmodus)])

_ROLLEN_NAME = {
    dienst.Rolle.ROOT: "root",
    dienst.Rolle.ADMIN: "admin",
    dienst.Rolle.KURSLEITER: "kursleiter",
    dienst.Rolle.TEILNEHMEND: "teilnehmend",
}
RollenName = Literal["root", "admin", "kursleiter", "teilnehmend"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


async def _person(user=Depends(get_authenticated_user)) -> PublicUser:
    """A signed-in person; API tokens (org or superadmin) are not a person here."""
    if not isinstance(user, PublicUser) or not user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=dienst.NICHT_ERLAUBT)
    return user


def _basis(env: str) -> str:
    basis = os.environ.get(env, "").strip().rstrip("/")
    if not basis:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"{env} is not configured")
    return basis


def _einladung_url(basis: str, token: str) -> str:
    return f"{basis}/einladung/{token}"


def _uebergabe_url(basis: str, actor_id: str, course_id: str) -> str:
    return f"{basis}/lernen/uebergabe/{uebergabe_token(actor_id, course_id)}"


def _verweigert(fehler: dienst.Verweigert) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=fehler.text)


def _link_ungueltig(fehler: dienst.LinkUngueltig) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_410_GONE, content={"detail": fehler.text, "grund": fehler.grund}
    )


def _kennung_vergeben() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="learner id is already assigned to another account"
    )


# --- Course overview and hand-over -----------------------------------------------------


class KursRead(BaseModel):
    course_id: str
    course_uuid: str
    titel: str
    gruppen: list[str]


class AnbieterRolleRead(BaseModel):
    org_id: int
    org_name: str
    rolle: RollenName


class KursuebersichtRead(BaseModel):
    kurse: list[KursRead]
    rollen: list[AnbieterRolleRead]


@router.get("/verwaltung/kursuebersicht", response_model=KursuebersichtRead)
async def get_kursuebersicht(
    user: PublicUser = Depends(_person),
    db_session: AsyncSession = Depends(get_db_session),
) -> KursuebersichtRead:
    kurse = await dienst.kurse_der_person(db_session, user)
    rollen = await dienst.rollen_der_person(db_session, user)
    return KursuebersichtRead(
        kurse=[KursRead(course_id=k.course_id, course_uuid=k.course_uuid, titel=k.titel, gruppen=k.gruppen)
               for k in kurse],
        rollen=[AnbieterRolleRead(org_id=r.org_id, org_name=r.org_name, rolle=_ROLLEN_NAME[r.rolle])
                for r in rollen],
    )


class UebergabeWrite(_Strict):
    course_id: str = Field(min_length=1, max_length=80)


class UrlRead(BaseModel):
    url: str


@router.post("/uebergabe", response_model=UrlRead)
async def post_uebergabe(
    payload: UebergabeWrite,
    user: PublicUser = Depends(_person),
    db_session: AsyncSession = Depends(get_db_session),
) -> UrlRead:
    """A one-click link that opens this course on the person's own Lern-Hülle (120 s)."""
    basis = _basis(HUELLE_BASIS_ENV)
    kurse = await dienst.kurse_der_person(db_session, user)
    if payload.course_id not in {k.course_id for k in kurse}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=dienst.NICHT_ERLAUBT)
    try:
        actor_id = await actor_von(db_session, user)
    except KennungVergeben:
        raise _kennung_vergeben() from None
    return UrlRead(url=_uebergabe_url(basis, actor_id, payload.course_id))


# --- Links --------------------------------------------------------------------------------


class LinkWrite(_Strict):
    art: Literal["admin", "kursleiter"]
    org_id: int = Field(gt=0)


class LinkErzeugtRead(BaseModel):
    link_id: int
    url: str
    laeuft_ab: datetime | None


class LinkRead(BaseModel):
    link_id: int
    art: str
    gruppe_id: int | None
    gruppe: str | None
    erstellt_am: datetime
    laeuft_ab: datetime | None


@router.post("/verwaltung/links", response_model=LinkErzeugtRead)
async def post_link(
    payload: LinkWrite,
    user: PublicUser = Depends(_person),
    db_session: AsyncSession = Depends(get_db_session),
) -> LinkErzeugtRead:
    basis = _basis(WEB_BASIS_ENV)
    try:
        link, token = await dienst.link_erzeugen(db_session, user, payload.art, payload.org_id)
    except dienst.Verweigert as fehler:
        raise _verweigert(fehler) from None
    return LinkErzeugtRead(
        link_id=int(link.id), url=_einladung_url(basis, token),
        laeuft_ab=dienst._utc(link.laeuft_ab) if link.laeuft_ab is not None else None,
    )


@router.delete("/verwaltung/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    link_id: int,
    user: PublicUser = Depends(_person),
    db_session: AsyncSession = Depends(get_db_session),
) -> Response:
    try:
        await dienst.link_zurueckziehen(db_session, user, link_id)
    except dienst.Verweigert as fehler:
        raise _verweigert(fehler) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/verwaltung/links", response_model=list[LinkRead])
async def get_links(
    org_id: Annotated[int, Query(gt=0)],
    user: PublicUser = Depends(_person),
    db_session: AsyncSession = Depends(get_db_session),
) -> list[LinkRead]:
    try:
        links = await dienst.aktive_links(db_session, user, org_id)
    except dienst.Verweigert as fehler:
        raise _verweigert(fehler) from None
    return [
        LinkRead(link_id=l.link_id, art=l.art, gruppe_id=l.gruppe_id, gruppe=l.gruppe,
                 erstellt_am=l.erstellt_am, laeuft_ab=l.laeuft_ab)
        for l in links
    ]


# --- Groups ---------------------------------------------------------------------------------


class GruppeWrite(_Strict):
    org_id: int = Field(gt=0)
    course_uuid: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)


class GruppeErzeugtRead(BaseModel):
    gruppe_id: int
    url: str


@router.post("/verwaltung/gruppen", response_model=GruppeErzeugtRead)
async def post_gruppe(
    payload: GruppeWrite,
    user: PublicUser = Depends(_person),
    db_session: AsyncSession = Depends(get_db_session),
) -> GruppeErzeugtRead:
    basis = _basis(WEB_BASIS_ENV)
    try:
        gruppe, token = await dienst.gruppe_anlegen(
            db_session, user, payload.org_id, payload.course_uuid, payload.name
        )
    except dienst.Verweigert as fehler:
        raise _verweigert(fehler) from None
    except ValueError:
        raise HTTPException(
            status_code=422, detail="group name is empty"
        ) from None
    return GruppeErzeugtRead(gruppe_id=int(gruppe.id), url=_einladung_url(basis, token))


@router.post("/verwaltung/gruppen/{gruppe_id}/schliessen", status_code=status.HTTP_204_NO_CONTENT)
async def post_gruppe_schliessen(
    gruppe_id: int,
    user: PublicUser = Depends(_person),
    db_session: AsyncSession = Depends(get_db_session),
) -> Response:
    try:
        await dienst.gruppe_schliessen(db_session, user, gruppe_id)
    except dienst.Verweigert as fehler:
        raise _verweigert(fehler) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- People ---------------------------------------------------------------------------------


class PersonRead(BaseModel):
    user_id: int
    anzeigename: str
    rolle: RollenName
    gruppen: list[str]


@router.get("/verwaltung/personen", response_model=list[PersonRead])
async def get_personen(
    org_id: Annotated[int, Query(gt=0)],
    user: PublicUser = Depends(_person),
    db_session: AsyncSession = Depends(get_db_session),
) -> list[PersonRead]:
    try:
        personen = await dienst.personen_des_anbieters(db_session, user, org_id)
    except dienst.Verweigert as fehler:
        raise _verweigert(fehler) from None
    return [
        PersonRead(user_id=p.user_id, anzeigename=p.anzeigename, rolle=_ROLLEN_NAME[p.rolle], gruppen=p.gruppen)
        for p in personen
    ]


@router.delete("/verwaltung/personen/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_person(
    user_id: int,
    org_id: Annotated[int, Query(gt=0)],
    user: PublicUser = Depends(_person),
    db_session: AsyncSession = Depends(get_db_session),
) -> Response:
    try:
        await dienst.person_entfernen(db_session, user, org_id, user_id)
    except dienst.Verweigert as fehler:
        raise _verweigert(fehler) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Invitations ----------------------------------------------------------------------------


class EinladungRead(BaseModel):
    art: str
    anbieter: str
    kurs: str | None


class EinloesungRead(BaseModel):
    org_id: int
    rolle: RollenName
    gruppe_id: int | None
    course_id: str | None
    uebergabe_url: str | None = None


class KontoWrite(_Strict):
    email: EmailStr
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


@router.get("/einladung/{token}", response_model=EinladungRead)
async def get_einladung(
    token: str,
    db_session: AsyncSession = Depends(get_db_session),
):
    """What a link invites to; public, so the page can greet before sign-in."""
    try:
        link, gruppe = await dienst.gueltiger_link(db_session, token)
    except dienst.LinkUngueltig as fehler:
        return _link_ungueltig(fehler)
    anbieter = await db_session.get(Organization, link.org_id)
    kurs = await db_session.get(Course, gruppe.course_id) if gruppe is not None else None
    return EinladungRead(
        art=link.art, anbieter=anbieter.name if anbieter is not None else "",
        kurs=kurs.name if kurs is not None else None,
    )


async def _einloesung_read(
    db_session: AsyncSession, user: PublicUser | User, einloesung: dienst.Einloesung
) -> EinloesungRead:
    url = None
    basis = os.environ.get(HUELLE_BASIS_ENV, "").strip().rstrip("/")
    if einloesung.course_id is not None and basis:
        try:
            url = _uebergabe_url(basis, await actor_von(db_session, user), einloesung.course_id)
        except KennungVergeben:
            url = None  # the redemption stands; the course overview reports the conflict
    return EinloesungRead(
        org_id=einloesung.org_id, rolle=_ROLLEN_NAME[einloesung.rolle], gruppe_id=einloesung.gruppe_id,
        course_id=einloesung.course_id, uebergabe_url=url,
    )


@router.post("/einladung/{token}/annehmen", response_model=EinloesungRead)
async def post_einladung_annehmen(
    token: str,
    user: PublicUser = Depends(_person),
    db_session: AsyncSession = Depends(get_db_session),
):
    try:
        einloesung = await dienst.link_einloesen(db_session, token, user)
    except dienst.LinkUngueltig as fehler:
        return _link_ungueltig(fehler)
    return await _einloesung_read(db_session, user, einloesung)


@router.post("/einladung/{token}/konto", response_model=EinloesungRead)
async def post_einladung_konto(
    token: str,
    payload: KontoWrite,
    request: Request,
    response: Response,
    db_session: AsyncSession = Depends(get_db_session),
):
    """A new account through a valid link: created, link redeemed, signed in like /auth/login."""
    try:
        link, _ = await dienst.gueltiger_link(db_session, token)
    except dienst.LinkUngueltig as fehler:
        return _link_ungueltig(fehler)
    org_id = int(link.org_id)

    # The same gates as the invite signup route (routers/users.py): throttle per IP and
    # provider, and no password account in a provider that refuses password sign-in.
    erlaubt, retry_after = check_invite_acceptance_rate_limit(request, org_id)
    if not erlaubt:
        minuten = max(1, retry_after // 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many invite attempts. Please try again in about {minuten} minute"
                   f"{'s' if minuten != 1 else ''}.",
            headers={"Retry-After": str(retry_after)},
        )
    await enforce_login_auth_method(db_session, org_id, AUTH_METHOD_PASSWORD)

    neu = await create_user(
        request, db_session, AnonymousUser(),
        UserCreate(email=payload.email, username=payload.username, password=payload.password),
        org_id, signup_provider="invite",
    )
    try:
        einloesung = await dienst.link_einloesen(db_session, token, neu)
    except dienst.LinkUngueltig as fehler:
        # Withdrawn in between: create_user's Teilnehmende membership must not outlive the link.
        await db_session.execute(
            delete(UserOrganization).where(
                UserOrganization.user_id == neu.id, UserOrganization.org_id == org_id
            )
        )
        await db_session.commit()
        return _link_ungueltig(fehler)

    konto = (await db_session.execute(select(User).where(User.id == neu.id))).scalars().one()
    issue = await issue_session_or_challenge(db_session, konto, amr=AUTH_METHOD_PASSWORD, org_id=org_id)
    if not issue.mfa_required:  # a brand-new account has no second factor yet
        set_auth_cookies(response, issue.access_token, issue.refresh_token, request)
    return await _einloesung_read(db_session, neu, einloesung)


# --- Providers (Root only) ------------------------------------------------------------------


class AnbieterWrite(_Strict):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")


class AnbieterRead(BaseModel):
    org_id: int
    admin_link_url: str


@router.post(
    "/anbieter",
    response_model=AnbieterRead,
    dependencies=[Depends(require_local_learning_bootstrap)],
)
async def post_anbieter(
    payload: AnbieterWrite,
    request: Request,
    user: PublicUser = Depends(_person),
    db_session: AsyncSession = Depends(get_db_session),
) -> AnbieterRead:
    """A new provider (setup only): bootstrap key and the signed-in superadmin, both required.

    Built by ``create_org``; only its edition lock is lifted, and only in the learning mode."""
    if not await dienst.ist_root(db_session, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=dienst.NICHT_ERLAUBT)
    basis = _basis(WEB_BASIS_ENV)
    anbieter = await create_org(
        request,
        OrganizationCreate(name=payload.name, slug=payload.slug, email=""),
        user,
        db_session,
        allow_multi_org=is_local_learning_mode_enabled(),
        skip_free_org_cap=is_local_learning_mode_enabled(),
    )
    try:
        link, token = await dienst.link_erzeugen(db_session, user, "admin", int(anbieter.id))
    except dienst.Verweigert as fehler:
        raise _verweigert(fehler) from None
    return AnbieterRead(org_id=int(anbieter.id), admin_link_url=_einladung_url(basis, token))

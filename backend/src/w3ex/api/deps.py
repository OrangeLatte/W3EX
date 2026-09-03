from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from w3ex.config import Settings, get_settings
from w3ex.db.session import get_db_session
from w3ex.providers.factory import ProviderBundle
from w3ex.providers.mock.generator import MockDataset

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_providers() -> ProviderBundle:
    return ProviderBundle.from_settings()


def get_dataset() -> MockDataset:
    return MockDataset()


SettingsDep = Annotated[Settings, Depends(get_settings)]
ProvidersDep = Annotated[ProviderBundle, Depends(get_providers)]
DatasetDep = Annotated[MockDataset, Depends(get_dataset)]

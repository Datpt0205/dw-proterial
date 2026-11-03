"""`PeoplePort` over the platform's workspace directory: who a member is, as
the directory the identity plane writes says."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from dw_platform.application.access_context import AccessContext
from dw_platform.application.ports import WorkspaceDirectoryPort
from dw_purchasing.application.ports import Person


@dataclass(frozen=True)
class DirectoryPeople:
    """Implements `PeoplePort`."""

    directory: WorkspaceDirectoryPort

    async def person(self, context: AccessContext, user_id: uuid.UUID) -> Person | None:
        for member in await self.directory.list_members(context):
            if member.user_id == user_id:
                return Person(member.display_name, member.department or "", member.email)
        return None

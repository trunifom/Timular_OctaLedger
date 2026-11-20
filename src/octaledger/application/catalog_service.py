"""Management of activities and projects (the "catalog" users book time against).

Responsibility
--------------
Create, rename, recolour, archive, restore and delete activities and projects. Items that
are already used by sessions or face mappings are **archived instead of deleted** (the
database enforces this with ``ON DELETE RESTRICT``; this service turns the technical
conflict into a clear message). New items without an explicit colour get the next colour
of a fixed, colour-blind-friendly palette so charts stay distinguishable.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Final

from octaledger.core.errors import ConflictError
from octaledger.domain.models import Activity, Project
from octaledger.infrastructure.storage.repositories import Repositories, Storage

logger = logging.getLogger(__name__)

#: Okabe-Ito based palette: distinguishable for common colour-vision deficiencies.
PALETTE: Final = (
    "#0072B2",
    "#E69F00",
    "#009E73",
    "#D55E00",
    "#CC79A7",
    "#56B4E9",
    "#F0E442",
    "#7F7F7F",
)


class CatalogService:
    """Use cases for activities and projects."""

    def __init__(self, storage: Storage) -> None:
        """Create the service on top of ``storage``."""
        self._storage = storage

    @staticmethod
    def _next_color(repos: Repositories) -> str:
        """Pick the palette colour used least often so far (stable, cycles)."""
        used = [i.color for i in repos.activities.list_all(include_archived=True)] + [
            i.color for i in repos.projects.list_all(include_archived=True)
        ]
        return min(PALETTE, key=lambda color: (used.count(color), PALETTE.index(color)))

    # ------------------------------------------------------------------ activities

    def create_activity(self, name: str, color: str | None = None) -> Activity:
        """Create an activity.

        Raises:
            ValidationError: For an invalid name or colour.
            ConflictError: If a non-archived activity has the same name.
        """
        with self._storage.transaction() as repos:
            return repos.activities.add(Activity(name=name, color=color or self._next_color(repos)))

    def list_activities(self, *, include_archived: bool = False) -> list[Activity]:
        """Return activities ordered by name."""
        with self._storage.read() as repos:
            return repos.activities.list_all(include_archived=include_archived)

    def update_activity(
        self, activity_id: str, *, name: str | None = None, color: str | None = None
    ) -> Activity:
        """Rename and/or recolour an activity."""
        with self._storage.transaction() as repos:
            current = repos.activities.require(activity_id)
            return repos.activities.update(
                replace(current, name=name or current.name, color=color or current.color)
            )

    def archive_activity(self, activity_id: str, archived: bool = True) -> Activity:
        """Archive (hide from selection lists) or restore an activity."""
        with self._storage.transaction() as repos:
            return repos.activities.set_archived(activity_id, archived)

    def delete_activity(self, activity_id: str) -> None:
        """Delete an unused activity; used ones must be archived.

        Raises:
            ConflictError: With a hint to archive if the activity is in use.
        """
        self._delete("activity", activity_id)

    # --------------------------------------------------------------------- projects

    def create_project(self, name: str, color: str | None = None) -> Project:
        """Create a project (same rules as activities)."""
        with self._storage.transaction() as repos:
            return repos.projects.add(Project(name=name, color=color or self._next_color(repos)))

    def list_projects(self, *, include_archived: bool = False) -> list[Project]:
        """Return projects ordered by name."""
        with self._storage.read() as repos:
            return repos.projects.list_all(include_archived=include_archived)

    def update_project(
        self, project_id: str, *, name: str | None = None, color: str | None = None
    ) -> Project:
        """Rename and/or recolour a project."""
        with self._storage.transaction() as repos:
            current = repos.projects.require(project_id)
            return repos.projects.update(
                replace(current, name=name or current.name, color=color or current.color)
            )

    def archive_project(self, project_id: str, archived: bool = True) -> Project:
        """Archive or restore a project."""
        with self._storage.transaction() as repos:
            return repos.projects.set_archived(project_id, archived)

    def delete_project(self, project_id: str) -> None:
        """Delete an unused project; used ones must be archived."""
        self._delete("project", project_id)

    # --------------------------------------------------------------------- internals

    def _delete(self, kind: str, item_id: str) -> None:
        """Delete with a clear message when the item is still referenced."""
        try:
            with self._storage.transaction() as repos:
                repo = repos.activities if kind == "activity" else repos.projects
                repo.delete(item_id, repos.audit)
        except ConflictError as exc:
            german = "Diese Tätigkeit" if kind == "activity" else "Dieses Projekt"
            raise ConflictError(
                f"{kind} {item_id} is still in use",
                user_message=(
                    f"{german} wird bereits verwendet und kann nicht gelöscht werden. "
                    "Bitte archivieren Sie sie stattdessen."
                ),
                details={"id": item_id, "kind": kind},
            ) from exc
        logger.info("Deleted unused %s %s", kind, item_id[:8])

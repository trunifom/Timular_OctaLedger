"""Tags, note templates and project billing (use cases).

Changes are transactional and audited where they touch booked time (the tags of an entry).
Activities and projects are validated to exist (a clear message instead of a foreign-key error).
"""

from __future__ import annotations

import logging

from octaledger.core.errors import ValidationError
from octaledger.domain.tags import MAX_TEMPLATE, ProjectBilling, Tag
from octaledger.infrastructure.storage.repositories import Repositories, Storage

logger = logging.getLogger(__name__)

#: A generous cap so the tag lists stay usable.
MAX_TAGS = 500
DEFAULT_TAG_COLOR = "#7F7F7F"


class TagService:
    """Tags, templates and billing."""

    def __init__(self, storage: Storage) -> None:
        """Create the service on top of ``storage``."""
        self._storage = storage

    # ------------------------------------------------------------------------ tags
    def list_tags(self) -> list[Tag]:
        """Return all tags by name."""
        with self._storage.read() as repos:
            return repos.tags.list_all()

    def create_tag(self, name: str, color: str | None = None) -> Tag:
        """Create a tag.

        Raises:
            ValidationError: For an invalid name/colour or too many tags.
            ConflictError: If the name exists already (case-insensitive).
        """
        with self._storage.transaction() as repos:
            if len(repos.tags.list_all()) >= MAX_TAGS:
                raise ValidationError(
                    "Too many tags",
                    user_message="Es gibt schon sehr viele Tags; löschen Sie ungenutzte.",
                )
            tag = repos.tags.add(Tag(name, color or DEFAULT_TAG_COLOR))
        logger.info("Tag created")
        return tag

    def update_tag(self, tag_id: str, name: str | None = None, color: str | None = None) -> Tag:
        """Rename or recolour a tag."""
        with self._storage.transaction() as repos:
            old = repos.tags.require(tag_id)
            return repos.tags.update(Tag(name or old.name, color or old.color, tag_id))

    def delete_tag(self, tag_id: str) -> None:
        """Delete a tag; it disappears from every entry and activity (the entries stay)."""
        with self._storage.transaction() as repos:
            tag = repos.tags.require(tag_id)
            repos.tags.delete(tag_id)
            repos.audit.add("delete_tag", "tag", tag_id, tag.name)

    # -------------------------------------------------------------- entries' tags
    def set_session_tags(self, session_id: str, tag_ids: list[str]) -> list[Tag]:
        """Replace the tags of an entry (audited).

        Raises:
            NotFoundError: If the entry or a tag does not exist.
        """
        with self._storage.transaction() as repos:
            repos.sessions.require(session_id)
            for tag_id in tag_ids:
                repos.tags.require(tag_id)
            repos.tags.set_session_tags(session_id, tag_ids)
            repos.audit.add("set_session_tags", "session", session_id, ",".join(tag_ids))
            return repos.tags.of_session(session_id)

    # ---------------------------------------------------- activity defaults/notes
    def get_activity_defaults(self, activity_id: str) -> dict[str, object]:
        """Return the default tags and the note template of an activity."""
        with self._storage.read() as repos:
            repos.activities.require(activity_id)
            return {
                "tags": repos.tags.activity_tags(activity_id),
                "note_template": repos.tags.note_template(activity_id),
            }

    def set_activity_defaults(
        self, activity_id: str, tag_ids: list[str], note_template: str | None
    ) -> None:
        """Set the tags new entries of the activity get and its note template.

        Raises:
            ValidationError: If the template is too long.
        """
        template = (note_template or "").strip() or None
        if template is not None and len(template) > MAX_TEMPLATE:
            raise ValidationError(
                "Template too long",
                user_message=f"Die Vorlage darf höchstens {MAX_TEMPLATE} Zeichen lang sein.",
            )
        with self._storage.transaction() as repos:
            repos.activities.require(activity_id)
            for tag_id in tag_ids:
                repos.tags.require(tag_id)
            repos.tags.set_activity_tags(activity_id, tag_ids)
            repos.tags.set_note_template(activity_id, template)

    @staticmethod
    def apply_default_tags(repos: Repositories, session_id: str, activity_id: str) -> None:
        """Give a new entry the default tags of its activity (same transaction as the entry)."""
        defaults = repos.tags.activity_tags(activity_id)
        if defaults:
            repos.tags.set_session_tags(session_id, [t.id for t in defaults])

    # ------------------------------------------------------------------ billing
    def get_billing(self, project_id: str) -> ProjectBilling:
        """Return budget, rate and billable flag of a project."""
        with self._storage.read() as repos:
            repos.projects.require(project_id)
            return repos.tags.billing(project_id)

    def set_billing(
        self,
        project_id: str,
        budget_minutes: int | None,
        hourly_rate_cents: int | None,
        billable: bool,
    ) -> ProjectBilling:
        """Set budget, rate and billable flag of a project (empty values remove them)."""
        billing = ProjectBilling(project_id, budget_minutes, hourly_rate_cents, billable)
        with self._storage.transaction() as repos:
            repos.projects.require(project_id)
            repos.tags.set_billing(billing)
            repos.audit.add("set_billing", "project", project_id)
        return billing

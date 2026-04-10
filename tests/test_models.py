from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from agent_hooks.models import Base, HookEvent, Request, Session


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine for model verification.

    :return: SQLite engine with the ORM schema created.
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


class TestModelSchema:
    def test_tables_match_the_adr(self, engine) -> None:
        inspector = inspect(engine)

        assert sorted(inspector.get_table_names()) == ["hook_event", "request", "session"]

        session_columns = {column["name"] for column in inspector.get_columns("session")}
        assert session_columns == {
            "created_at",
            "cwd",
            "id",
            "last_seen_at",
            "permission_mode",
            "provider",
            "provider_session_id",
            "transcript_path",
            "updated_at",
        }

        hook_event_columns = {column["name"] for column in inspector.get_columns("hook_event")}
        assert hook_event_columns == {
            "created_at",
            "display_json",
            "hook_event_name",
            "id",
            "payload_json",
            "processing_error",
            "session_id",
        }

        request_columns = {column["name"] for column in inspector.get_columns("request")}
        assert request_columns == {
            "answer_channel",
            "answer_choice",
            "answer_payload_json",
            "answered_at",
            "answered_by",
            "created_at",
            "hook_event_id",
            "hook_response_json",
            "id",
            "resolved_at",
            "session_id",
            "status",
            "suggestions_json",
            "tool_input_json",
            "tool_name",
            "updated_at",
        }

    def test_unique_constraints_match_the_adr(self, engine) -> None:
        inspector = inspect(engine)

        session_uniques = {
            tuple(item["column_names"]) for item in inspector.get_unique_constraints("session")
        }
        request_uniques = {
            tuple(item["column_names"]) for item in inspector.get_unique_constraints("request")
        }

        assert ("provider_session_id",) in session_uniques
        assert ("hook_event_id",) in request_uniques


class TestModelRelationships:
    def test_permission_request_round_trips_across_relationships(self, engine) -> None:
        with OrmSession(engine) as database_session:
            provider_session = Session(provider="claude", provider_session_id="session-1")
            database_session.add(provider_session)
            database_session.flush()

            hook_event = HookEvent(
                session=provider_session,
                hook_event_name="PermissionRequest",
                payload_json='{"tool_name":"Bash"}',
            )
            database_session.add(hook_event)
            database_session.flush()

            request = Request(
                hook_event=hook_event,
                session=provider_session,
                status="pending",
                tool_name="Bash",
            )
            database_session.add(request)
            database_session.commit()

            stored_session = database_session.get(Session, provider_session.id)
            stored_request = database_session.get(Request, request.id)
            stored_hook_event = database_session.get(HookEvent, hook_event.id)

            assert stored_session is not None
            assert stored_request is not None
            assert stored_hook_event is not None
            assert stored_hook_event.request is not None
            assert stored_session.hook_events[0].id == stored_hook_event.id
            assert stored_session.requests[0].id == stored_request.id
            assert stored_request.hook_event.id == stored_hook_event.id
            assert stored_hook_event.request.id == stored_request.id
            assert stored_session.created_at
            assert stored_session.updated_at
            assert stored_session.last_seen_at
            assert stored_hook_event.created_at
            assert stored_request.created_at
            assert stored_request.updated_at

    def test_request_enforces_one_to_one_hook_event_link(self, engine) -> None:
        with OrmSession(engine) as database_session:
            provider_session = Session(provider="claude", provider_session_id="session-1")
            hook_event = HookEvent(
                session=provider_session,
                hook_event_name="PermissionRequest",
                payload_json="{}",
            )
            first_request = Request(
                hook_event=hook_event,
                session=provider_session,
                status="pending",
            )

            database_session.add_all([provider_session, hook_event, first_request])
            database_session.flush()

            database_session.add(
                Request(
                    hook_event_id=hook_event.id,
                    session_id=provider_session.id,
                    status="pending",
                )
            )

            with pytest.raises(IntegrityError):
                database_session.flush()

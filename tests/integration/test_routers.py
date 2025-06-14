import pytest
from unittest.mock import Mock, patch

from tests.fixtures.test_data import create_test_company, create_test_publication


class TestHealthRouter:
    def test_health_check(self, client):
        """Test health endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "OK"}


class TestCompanyRouter:
    def test_get_company_authenticated(self, client, db_session, mock_clerk):
        """Test getting company info as authenticated user."""
        company = create_test_company(db_session, emails=["test@company.com"])

        response = client.get(
            "/company/", headers={"Authorization": "Bearer test-token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["vat_number"] == company.vat_number
        assert data["name"] == company.name

    def test_update_company(self, client, db_session, mock_clerk):
        """Test updating company information."""
        company = create_test_company(db_session, emails=["test@company.com"])

        update_data = {"number_of_employees": 100, "max_publication_value": 500000}

        response = client.put(
            f"/company/{company.vat_number}",
            json=update_data,
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["number_of_employees"] == 100
        assert data["max_publication_value"] == 500000

    def test_scrape_website(self, client, db_session, mock_clerk):
        """Test website scraping endpoint."""
        company = create_test_company(db_session, emails=["test@company.com"])

        with patch("app.ai.scraper.scrape_company_website") as mock_scrape:
            mock_scrape.return_value = {
                "activities": "Construction services",
                "keywords": ["construction", "building"],
            }

            response = client.post(
                "/company/scrape-website",
                json={"website_url": "https://example.com"},
                headers={"Authorization": "Bearer test-token"},
            )

            assert response.status_code == 200
            assert (
                response.json()["message"]
                == "Website scraped and company profile updated successfully"
            )


class TestPublicationRouter:
    def test_get_publications(self, client, db_session, mock_clerk):
        """Test getting publications list."""
        company = create_test_company(db_session, emails=["test@company.com"])
        pub1 = create_test_publication(db_session)
        pub2 = create_test_publication(
            db_session, publication_workspace_id="2024-S-002-222222"
        )

        response = client.get(
            "/publications/?page=1&size=10",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data

    def test_get_publication_detail(self, client, db_session, mock_clerk):
        """Test getting publication details."""
        company = create_test_company(db_session, emails=["test@company.com"])
        publication = create_test_publication(db_session)

        response = client.get(
            f"/publications/{publication.publication_workspace_id}",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["publication_workspace_id"] == publication.publication_workspace_id

    def test_search_publications(self, client, db_session, mock_clerk):
        """Test searching publications."""
        company = create_test_company(db_session, emails=["test@company.com"])
        pub1 = create_test_publication(
            db_session, extracted_keywords=["highway", "construction"]
        )
        pub2 = create_test_publication(
            db_session,
            publication_workspace_id="2024-S-002-222222",
            extracted_keywords=["software", "IT"],
        )

        response = client.post(
            "/publications/search",
            json={"search_query": "construction", "page": 1, "size": 10},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 1

    def test_save_publication(self, client, db_session, mock_clerk):
        """Test saving a publication."""
        company = create_test_company(db_session, emails=["test@company.com"])
        publication = create_test_publication(db_session)

        response = client.post(
            f"/publications/{publication.publication_workspace_id}/save",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Publication saved successfully"


class TestConversationRouter:
    @pytest.fixture
    def mock_openai(self, mock_openai_client):
        """Configure mock OpenAI responses."""
        mock_assistant = Mock()
        mock_assistant.id = "asst_123"
        mock_openai_client.beta.assistants.create.return_value = mock_assistant

        mock_thread = Mock()
        mock_thread.id = "thread_123"
        mock_openai_client.beta.threads.create.return_value = mock_thread

        return mock_openai_client

    def test_create_conversation(self, client, db_session, mock_clerk):
        """Test creating a new conversation."""
        company = create_test_company(db_session, emails=["test@company.com"])
        publication = create_test_publication(db_session)

        response = client.post(
            f"/conversations/{publication.publication_workspace_id}/start",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["publication_workspace_id"] == publication.publication_workspace_id

    def test_send_chat_message(self, client, db_session, mock_clerk, mock_openai):
        """Test sending a chat message."""
        company = create_test_company(db_session, emails=["test@company.com"])
        publication = create_test_publication(db_session)

        # Create conversation first
        conv_response = client.post(
            f"/conversations/{publication.publication_workspace_id}/start",
            headers={"Authorization": "Bearer test-token"},
        )
        conversation_id = conv_response.json()["id"]

        # Mock AI response
        mock_message = Mock()
        mock_message.content = [Mock(text=Mock(value="This is an AI response"))]
        mock_openai.beta.threads.messages.list.return_value = [mock_message]

        mock_run = Mock()
        mock_run.status = "completed"
        mock_openai.beta.threads.runs.create_and_poll.return_value = mock_run

        # Send message
        response = client.post(
            f"/conversations/{conversation_id}/chat",
            json={"message": "Tell me about this tender"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert data["response"] == "This is an AI response"


class TestNotificationRouter:
    def test_get_notifications(self, client, db_session, mock_clerk):
        """Test getting user notifications."""
        company = create_test_company(db_session, emails=["test@company.com"])

        response = client.get(
            "/notifications/", headers={"Authorization": "Bearer test-token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "unread" in data

    def test_mark_notification_read(self, client, db_session, mock_clerk):
        """Test marking notification as read."""
        from app.models.notification_models import Notification

        company = create_test_company(db_session, emails=["test@company.com"])

        # Create a notification
        notification = Notification(
            company_vat_number=company.vat_number,
            title="New Publication Match",
            content="A new publication matches your profile",
            notification_type="publication_match",
            is_read=False,
        )
        db_session.add(notification)
        db_session.commit()

        response = client.put(
            f"/notifications/{notification.id}/read",
            headers={"Authorization": "Bearer test-token"},
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Notification marked as read"

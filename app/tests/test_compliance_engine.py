import unittest
from unittest.mock import MagicMock, patch
import uuid
from app.services.review_engine import ComplianceReviewer
from app.models.tables import SectionContent, Requirement

class TestComplianceReviewer(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.reviewer = ComplianceReviewer(self.mock_db)
        self.project_id = str(uuid.uuid4())
        self.section_id = str(uuid.uuid4())

    @patch("app.services.review_engine.resolve_profile_chain_for_task")
    @patch("app.services.review_engine.compliance_review_with_fallback_chain")
    def test_review_section_success(self, mock_review, mock_resolve):
        # Setup mocks
        mock_section = SectionContent()
        mock_section.id = uuid.UUID(self.section_id)
        mock_section.project_id = uuid.UUID(self.project_id)
        mock_section.section_key = "1.1"
        mock_section.content_md = "Some content"
        mock_section.requirement_codes = ["REQ-01"]
        mock_section.version_id = uuid.uuid4()
        
        self.mock_db.scalar.return_value = mock_section
        
        mock_req = Requirement()
        mock_req.requirement_code = "REQ-01"
        mock_req.original_text = "Must compliant"
        mock_req.strength = MagicMock()
        mock_req.strength.name = "MUST"
        
        self.mock_db.scalars.return_value.all.return_value = [mock_req]
        
        mock_result = MagicMock()
        mock_result.status = "PASS"
        mock_result.report = {"approved": True}
        mock_review.return_value = (mock_result, 0)
        
        # Execute
        report = self.reviewer.review_section(self.project_id, self.section_id)
        
        # Verify
        self.assertEqual(report.status, "PASS")
        self.assertEqual(report.section_key, "1.1")
        self.mock_db.add.assert_called_once()
        self.mock_db.commit.assert_called_once()

    def test_review_section_not_found(self):
        self.mock_db.scalar.return_value = None
        with self.assertRaises(ValueError):
            self.reviewer.review_section(self.project_id, self.section_id)

    def test_review_section_no_requirements(self):
        mock_section = SectionContent()
        mock_section.id = uuid.UUID(self.section_id)
        mock_section.project_id = uuid.UUID(self.project_id)
        mock_section.section_key = "1.1"
        mock_section.requirement_codes = []
        mock_section.version_id = uuid.uuid4()
        
        self.mock_db.scalar.return_value = mock_section
        
        report = self.reviewer.review_section(self.project_id, self.section_id)
        
        self.assertEqual(report.status, "PASS")
        self.assertIn("No requirements mapped", report.report_json["general_comments"])

    @patch("app.services.review_engine.resolve_profile_chain_for_task")
    @patch("app.services.review_engine.compliance_review_with_fallback_chain")
    def test_review_section_respects_outline_id(self, mock_review, mock_resolve):
        mock_section = SectionContent()
        mock_section.id = uuid.UUID(self.section_id)
        mock_section.project_id = uuid.UUID(self.project_id)
        mock_section.section_key = "1.1"
        mock_section.content_md = "Some content"
        mock_section.requirement_codes = ["REQ-01"]
        mock_section.version_id = uuid.uuid4()

        self.mock_db.scalar.return_value = mock_section

        mock_req = Requirement()
        mock_req.requirement_code = "REQ-01"
        mock_req.original_text = "Must compliant"
        mock_req.strength = MagicMock()
        mock_req.strength.name = "MUST"
        self.mock_db.scalars.return_value.all.return_value = [mock_req]

        mock_result = MagicMock()
        mock_result.status = "PASS"
        mock_result.report = {"approved": True}
        mock_review.return_value = (mock_result, 0)

        report = self.reviewer.review_section(self.project_id, self.section_id, outline_id="outline-abc")

        self.assertEqual(report.outline_id, "outline-abc")

if __name__ == "__main__":
    unittest.main()

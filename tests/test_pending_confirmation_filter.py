"""Tests for the sidebar 'needs confirmation' badge's backing data:
count_pending_uploads() and the 'awaiting_confirmation' history status filter.
"""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'ui'))

_test_dir = tempfile.mkdtemp()
os.environ['DATA_DIR'] = _test_dir

from database import (  # noqa: E402
    init_db, create_job, update_job_progress, create_pending_upload,
    count_pending_uploads, get_combined_history_and_jobs,
    get_combined_history_and_jobs_count, get_db,
)

init_db()


class PendingConfirmationFilterTests(unittest.TestCase):
    def setUp(self):
        self.job_id = create_job('https://example.com/needs-confirmation')
        update_job_progress(
            self.job_id, 'awaiting_confirmation', 90, 'preview',
            'Waiting for confirmation')
        create_pending_upload(
            'upload-' + self.job_id, self.job_id, {'name': 'Test Recipe'},
            None, [], 'tandoor')

        self.other_job_id = create_job('https://example.com/still-processing')
        update_job_progress(
            self.other_job_id, 'transcribing', 40, 'transcribe', 'Transcribing...')

    def tearDown(self):
        with get_db() as conn:
            conn.execute("DELETE FROM pending_uploads WHERE job_id IN (?, ?)",
                         (self.job_id, self.other_job_id))
            conn.execute("DELETE FROM recipe_jobs WHERE id IN (?, ?)",
                         (self.job_id, self.other_job_id))
            conn.commit()

    def test_count_pending_uploads(self):
        self.assertGreaterEqual(count_pending_uploads(), 1)

    def test_awaiting_confirmation_filter_returns_only_that_job(self):
        items = get_combined_history_and_jobs(status_filter='awaiting_confirmation')
        job_ids = {item['job_id'] for item in items}
        self.assertIn(self.job_id, job_ids)
        self.assertNotIn(self.other_job_id, job_ids)

        count = get_combined_history_and_jobs_count(status_filter='awaiting_confirmation')
        self.assertGreaterEqual(count, 1)

    def test_processing_filter_excludes_awaiting_confirmation(self):
        items = get_combined_history_and_jobs(status_filter='processing')
        job_ids = {item['job_id'] for item in items}
        self.assertNotIn(self.job_id, job_ids)
        self.assertIn(self.other_job_id, job_ids)


if __name__ == "__main__":
    unittest.main()

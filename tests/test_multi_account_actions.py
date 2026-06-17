"""Multi-account live action routing over canonical composite ids."""

from __future__ import annotations

import unittest
from unittest import mock

from backend import mail_service


class CompositeIdHelperTests(unittest.TestCase):
    def test_split_composite_id_basic(self) -> None:
        self.assertEqual(
            mail_service._split_composite_id('acct-1|INBOX|42'),
            ('acct-1', 'INBOX', '42'),
        )

    def test_split_composite_id_preserves_mailbox_with_pipe(self) -> None:
        self.assertEqual(
            mail_service._split_composite_id('acct-1|Lists|News|7'),
            ('acct-1', 'Lists|News', '7'),
        )

    def test_split_composite_id_rejects_non_composite(self) -> None:
        self.assertIsNone(mail_service._split_composite_id('msg-1'))
        self.assertIsNone(mail_service._split_composite_id('only|one'))
        self.assertIsNone(mail_service._split_composite_id('|INBOX|1'))

    def test_plan_action_groups_separates_legacy_and_composite(self) -> None:
        groups, legacy = mail_service._plan_action_groups(
            ['acct-1|INBOX|10', 'acct-1|Archive|11', 'acct-2|INBOX|20', 'msg-1'])
        self.assertEqual(legacy, [('msg-1', 'msg-1')])
        self.assertEqual(groups[('acct-1', 'INBOX')], [('10', 'acct-1|INBOX|10')])
        self.assertEqual(groups[('acct-1', 'Archive')], [('11', 'acct-1|Archive|11')])
        self.assertEqual(groups[('acct-2', 'INBOX')], [('20', 'acct-2|INBOX|20')])


def _multi_account_settings() -> dict:
    return {
        'dummyMode': False,
        'mailAccounts': [
            {'id': 'acct-1', 'enabled': True, 'imapHost': 'imap1.example.com',
             'imapPort': 993, 'imapUseSSL': True, 'username': 'u1', 'imapPassword': 'p1'},
            {'id': 'acct-2', 'enabled': True, 'imapHost': 'imap2.example.com',
             'imapPort': 993, 'imapUseSSL': True, 'username': 'u2', 'imapPassword': 'p2'},
            {'id': 'acct-off', 'enabled': False, 'imapHost': 'imap3.example.com',
             'imapPort': 993, 'imapUseSSL': True, 'username': 'u3', 'imapPassword': 'p3'},
        ],
    }


class MultiAccountRoutingTests(unittest.TestCase):
    def _patched_imap(self):
        created: list[mock.MagicMock] = []

        def factory(host, port):
            conn = mock.MagicMock()
            conn._host = host
            conn.login.return_value = ('OK', [])
            conn.select.return_value = ('OK', [b'1'])
            conn.uid.return_value = ('OK', [])
            created.append(conn)
            return conn

        return created, mock.patch('imaplib.IMAP4_SSL', side_effect=factory)

    def test_mark_read_routes_per_account_and_mailbox(self) -> None:
        created, patcher = self._patched_imap()
        ids = ['acct-1|INBOX|10', 'acct-1|Archive|11', 'acct-2|INBOX|20']
        with patcher:
            result = mail_service.mark_messages_read(ids, _multi_account_settings())

        self.assertCountEqual(result['restore_unread_ids'], ids)
        self.assertEqual(result['failed_message_ids'], [])

        selections: list[tuple[str, str]] = []
        stores: list[tuple[str, str, str]] = []
        for conn in created:
            for call in conn.select.call_args_list:
                selections.append((conn._host, call.args[0]))
            for call in conn.uid.call_args_list:
                if call.args and call.args[0] == 'STORE':
                    stores.append((conn._host, call.args[1], call.args[3]))

        self.assertIn(('imap1.example.com', 'INBOX'), selections)
        self.assertIn(('imap1.example.com', 'Archive'), selections)
        self.assertIn(('imap2.example.com', 'INBOX'), selections)
        self.assertIn(('imap1.example.com', '10', '(\\Seen)'), stores)
        self.assertIn(('imap1.example.com', '11', '(\\Seen)'), stores)
        self.assertIn(('imap2.example.com', '20', '(\\Seen)'), stores)

    def test_add_tag_returns_composite_ids(self) -> None:
        _created, patcher = self._patched_imap()
        ids = ['acct-1|INBOX|10', 'acct-2|INBOX|20']
        with patcher:
            result = mail_service.add_keyword_tag(ids, 'important', _multi_account_settings())
        self.assertCountEqual(result['added_message_ids'], ids)
        self.assertEqual(result['failed_message_ids'], [])

    def test_unresolved_account_is_failed_not_raised(self) -> None:
        result = mail_service.mark_messages_read(['ghost|INBOX|1'], _multi_account_settings())
        self.assertEqual(result['restore_unread_ids'], [])
        self.assertEqual(result['failed_message_ids'], ['ghost|INBOX|1'])

    def test_disabled_account_is_failed(self) -> None:
        result = mail_service.mark_messages_read(['acct-off|INBOX|1'], _multi_account_settings())
        self.assertEqual(result['restore_unread_ids'], [])
        self.assertEqual(result['failed_message_ids'], ['acct-off|INBOX|1'])


if __name__ == '__main__':
    unittest.main()

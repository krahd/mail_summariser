"""Real Chromium interactions against the isolated demo; run in ordinary CI.

Only synthetic data and small screenshots are retained. This deliberately does
not launch browsers where local execution has been denied.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_full_stack import find_free_port, wait_for_url, terminate_process


def serve_fault_fixture(port: int, fault_file: Path):
    """CI-only fault injection, with no added HTTP routes or product switches."""
    os.environ['MAIL_SUMMARISER_DEMO'] = 'true'
    from unittest.mock import patch
    import uvicorn
    from backend import mail_index_service
    real_sync = mail_index_service.sync_mailbox

    def controlled_sync(*args, **kwargs):
        if fault_file.exists():
            fault_file.unlink()
            raise RuntimeError('Synthetic one-shot index failure')
        return real_sync(*args, **kwargs)

    mail_index_service.sync_mailbox = controlled_sync
    with patch('socket.socket.connect', side_effect=AssertionError('Outbound network forbidden')), \
         patch('socket.create_connection', side_effect=AssertionError('Outbound network forbidden')), \
         patch('backend.summary_service._summarize_with_provider', side_effect=AssertionError('Provider forbidden')), \
         patch('backend.routers_actions.send_summary_email', side_effect=AssertionError('SMTP forbidden')):
        uvicorn.run('backend.app:app', host='127.0.0.1', port=port, workers=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='demo-evidence')
    parser.add_argument('--serve-fault-fixture', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--fault-file', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve_fault_fixture:
        serve_fault_fixture(args.serve_fault_fixture, args.fault_file)
        return
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright, expect
    checks = []
    port = find_free_port('127.0.0.1')
    base = f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory(prefix='mail-demo-ui-') as tmp:
        fault_file = Path(tmp)/'fail-next-index-sync'
        with (Path(tmp)/'server.log').open('wb') as log:
            server = subprocess.Popen([sys.executable, 'scripts/validate_demo_ui.py', '--serve-fault-fixture', str(port), '--fault-file', str(fault_file)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            wait_for_url(base+'/health', attempts=80, delay_seconds=0.25, process=server)
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                context = browser.new_context(viewport={'width':1440, 'height':1000})
                context.add_init_script("localStorage.setItem('mail_summariser-base-url', 'https://invalid.example'); localStorage.setItem('mail_summariser-api-key', 'synthetic-not-a-key');")
                page = context.new_page()
                errors, external = [], []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.on('request', lambda req: external.append(req.url) if not req.url.startswith(base+'/') else None)
                page.route('**/mail/triage/dashboard*', lambda route: route.fulfill(status=503, content_type='application/json', body='{"detail":"Synthetic dashboard failure"}'))
                page.goto(base)
                expect(page.locator('#status-line')).to_contain_text('Triage dashboard failed')
                page.wait_for_timeout(150)
                expect(page.locator('#status-line')).not_to_contain_text('Sample inbox ready')
                page.unroute('**/mail/triage/dashboard*')
                page.locator('#demo-retry').click()
                expect(page.locator('#status-line')).to_contain_text('Sample inbox ready')
                checks.append('Initial dashboard failure remains an error; visible Reload recovers')
                expect(page.locator('#demo-onboarding')).to_be_visible()
                expect(page.locator('.tab[data-tab="settings"]')).to_be_hidden()
                assert len(page.request.get(base+'/mail/index/messages').json()) == 8
                assert page.request.get(base+'/mail/triage/dashboard').json()['totals']['unread'] == 6
                page.screenshot(path=str(output/'01-onboarding-desktop.png'), full_page=True)
                checks.append('First-run isolation, indexed fixtures, malicious stored backend ignored')

                page.locator('.triage-message-item').first.click()
                expect(page.locator('#triage-message-detail-body')).not_to_contain_text('Select a bucket')
                page.locator('[data-triage-summary-bucket-id="reply_needed_candidates"]').click()
                expect(page.locator('#tab-search')).to_have_class(__import__('re').compile(r'.*active.*'))
                expect(page.locator('#summary-text')).to_contain_text('local excerpts, no AI provider')
                expect(page.locator('#messages-body tr[data-message-id]')).not_to_have_count(0)
                checks.append('Triage evidence to local excerpt digest and source message')

                page.locator('#apply-scope-actions').click()
                expect(page.locator('#action-confirm-apply')).to_be_enabled()
                assert page.locator('#action-confirm-items li').count() > 0
                page.screenshot(path=str(output/'02-review-preview-desktop.png'), full_page=True)
                page.locator('#action-confirm-cancel').click()
                expect(page.locator('#action-confirm')).to_be_hidden()
                assert page.request.get(base+'/mail/triage/dashboard').json()['totals']['unread'] == 6
                checks.append('Per-message preview cancellation leaves mailbox unchanged')

                page.locator('#apply-scope-actions').click()
                expect(page.locator('#action-confirm-apply')).to_be_enabled()
                page.locator('#action-confirm-apply').click()
                expect(page.locator('#status-line')).to_contain_text('Safe mode: simulated only')
                assert page.request.get(base+'/mail/triage/dashboard').json()['totals']['unread'] == 6
                checks.append('Default safe mode simulates the whole action selection')

                page.locator('#demo-safe-mode').uncheck()
                expect(page.locator('#status-line')).to_contain_text('Changes enabled')
                page.locator('#apply-scope-actions').click()
                expect(page.locator('#action-confirm-apply')).to_be_enabled()
                page.locator('#action-confirm-apply').dblclick()
                expect(page.locator('#status-line')).to_contain_text('Applied:')
                assert page.request.get(base+'/mail/triage/dashboard').json()['totals']['unread'] < 6
                page.locator('#action-toast-undo').click()
                expect(page.locator('#status-line')).to_contain_text('Undone.')
                assert page.request.get(base+'/mail/triage/dashboard').json()['totals']['unread'] == 6
                checks.append('Apply, double-click suppression, grouped undo and index recovery')

                page.locator('#scope-action-tag').uncheck()
                page.locator('#apply-scope-actions').click()
                expect(page.locator('#action-confirm-apply')).to_be_enabled()
                fault_file.write_text('fail next sync')
                page.locator('#action-confirm-apply').click()
                expect(page.locator('#status-line')).to_contain_text('Action completed. Sample index refresh failed')
                assert page.request.get(base+'/mail/triage/dashboard').status == 503
                logs_after_apply = page.request.get(base+'/logs').json()
                fault_file.write_text('fail next sync')
                page.locator('#demo-sync').click()
                expect(page.locator('#status-line')).to_contain_text('Index rebuild failed')
                expect(page.locator('#demo-sync')).to_be_enabled()
                page.locator('#demo-retry').click()
                expect(page.locator('#status-line')).to_contain_text('Sample index is out of date')
                page.locator('#demo-sync').click()
                expect(page.locator('#status-line')).to_contain_text('Sample index rebuilt')
                assert page.request.get(base+'/logs').json() == logs_after_apply
                assert page.request.get(base+'/mail/triage/dashboard').json()['totals']['unread'] < 6
                fault_file.write_text('fail next sync')
                page.locator('#undo-action').click()
                expect(page.locator('#status-line')).to_contain_text('Undo completed. Sample index refresh failed')
                assert page.request.get(base+'/mail/triage/dashboard').status == 503
                logs_after_undo = page.request.get(base+'/logs').json()
                assert not any(entry['undoable'] for entry in logs_after_undo)
                page.locator('#demo-sync').click()
                expect(page.locator('#status-line')).to_contain_text('Sample index rebuilt')
                assert page.request.get(base+'/logs').json() == logs_after_undo
                assert page.request.get(base+'/mail/triage/dashboard').json()['totals']['unread'] == 6
                checks.append('Completed apply/undo plus actual index faults remain truthful; nondestructive rebuild retries preserve history')

                page.locator('#apply-scope-actions').click()
                expect(page.locator('#action-confirm-apply')).to_be_enabled()
                page.route('**/mail/triage/dashboard*', lambda route: route.fulfill(status=503, content_type='application/json', body='{"detail":"Synthetic view failure"}'))
                page.locator('#action-confirm-apply').click()
                expect(page.locator('#status-line')).to_contain_text('Dashboard refresh failed')
                expect(page.locator('#status-line')).to_contain_text('Applied:')
                page.unroute('**/mail/triage/dashboard*')
                page.locator('#demo-retry').click()
                expect(page.locator('#status-line')).to_contain_text('Sample inbox ready')
                page.locator('#undo-action').click()
                expect(page.locator('#status-line')).to_contain_text('Undone.')
                checks.append('Completed mutation plus failed view refresh never reports an unqualified ready state')


                held = []
                page.route('**/actions/jobs/*/preview', lambda route: held.append(route))
                page.locator('#apply-scope-actions').click()
                expect(page.locator('#action-confirm-summary')).to_contain_text('Preparing preview')
                page.locator('#action-confirm-cancel').click()
                assert held
                held[0].fulfill(response=held[0].fetch())
                page.wait_for_timeout(150)
                expect(page.locator('#action-confirm')).to_be_hidden()
                page.unroute('**/actions/jobs/*/preview')
                checks.append('Cancel in-flight preview prevents late confirmation reopening')

                previous_job = page.locator('#job-id').inner_text()
                held = []
                page.route('**/summaries', lambda route: held.append(route))
                page.locator('#search-form button[type="submit"]').click()
                expect(page.locator('#cancel-digest')).to_be_visible()
                page.locator('#cancel-digest').click()
                assert held
                held[0].fulfill(response=held[0].fetch())
                page.wait_for_timeout(150)
                assert page.locator('#job-id').inner_text() == previous_job
                page.unroute('**/summaries')
                checks.append('Cancel in-flight digest preserves previous review')

                held = []
                page.route('**/summaries', lambda route: held.append(route))
                page.locator('#search-form input[name="keyword"]').fill('Project')
                page.locator('#search-form button[type="submit"]').click()
                page.wait_for_timeout(100)
                page.locator('#search-form input[name="keyword"]').fill('Invoice')
                page.locator('#search-form button[type="submit"]').click()
                page.wait_for_timeout(100)
                assert len(held) == 2
                held[1].fulfill(response=held[1].fetch())
                expect(page.locator('#summary-text')).to_contain_text('Invoice line items')
                newer_job = page.locator('#job-id').inner_text()
                held[0].fulfill(response=held[0].fetch())
                page.wait_for_timeout(150)
                assert page.locator('#job-id').inner_text() == newer_job
                expect(page.locator('#summary-text')).to_contain_text('Invoice line items')
                page.unroute('**/summaries')
                checks.append('Out-of-order digest responses cannot replace newer selection')

                page.route('**/summaries', lambda route: route.fulfill(status=503, content_type='application/json', body='{"detail":"Synthetic service interruption"}'))
                page.locator('#search-form button[type="submit"]').click()
                expect(page.locator('#status-line')).to_contain_text('Synthetic service interruption')
                assert page.locator('#job-id').inner_text() == newer_job
                page.unroute('**/summaries')
                page.locator('#search-form button[type="submit"]').click()
                expect(page.locator('#status-line')).to_contain_text('Summary created')
                checks.append('Failed summary retains previous result and explicit retry recovers')

                page.locator('#apply-scope-actions').click()
                expect(page.locator('#action-confirm-apply')).to_be_enabled()
                page.route('**/actions/jobs/*/apply', lambda route: route.fulfill(status=503, content_type='application/json', body='{"detail":"Synthetic action interruption"}'))
                page.locator('#action-confirm-apply').click()
                expect(page.locator('#status-line')).to_contain_text('Inspect Log before retrying')
                expect(page.locator('#apply-scope-actions')).to_be_enabled()
                page.unroute('**/actions/jobs/*/apply')
                page.locator('#apply-scope-actions').click()
                expect(page.locator('#action-confirm-apply')).to_be_enabled()
                page.locator('.tab[data-tab="logs"]').click()
                expect(page.locator('#action-confirm')).to_be_hidden()
                checks.append('Action failure is recoverable; navigating away invalidates confirmation')

                page.once('dialog', lambda d: d.dismiss())
                page.locator('#demo-reset').click()
                assert len(page.request.get(base+'/logs').json()) > 0
                page.once('dialog', lambda d: d.accept())
                page.locator('#demo-reset').click()
                expect(page.locator('#status-line')).to_contain_text('Eight fictional messages restored')
                expect(page.locator('#demo-safe-mode')).to_be_checked()
                assert page.request.get(base+'/logs').json() == []
                checks.append('Reset cancellation and confirmed reset restore safe onboarding')

                page.set_viewport_size({'width':390, 'height':844})
                expect(page.locator('#demo-onboarding')).to_be_visible()
                page.screenshot(path=str(output/'03-onboarding-mobile.png'), full_page=True)
                metrics = page.evaluate('''() => ({width:innerWidth, scrollWidth:document.documentElement.scrollWidth,
                    overflow:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right > innerWidth+1).map(e=>({tag:e.tagName,id:e.id,cls:e.className,right:e.getBoundingClientRect().right,whiteSpace:getComputedStyle(e).whiteSpace})).slice(0,25)})''')
                (output/'mobile-layout.json').write_text(json.dumps(metrics, indent=2))
                assert metrics['scrollWidth'] <= metrics['width'] + 1, metrics
                page.locator('[data-triage-summary-bucket-id="reply_needed_candidates"]').click()
                expect(page.locator('#summary-text')).to_contain_text('local excerpts')
                page.locator('#apply-scope-actions').click()
                expect(page.locator('#action-confirm-apply')).to_be_enabled()
                page.locator('#action-confirm-cancel').click()
                expect(page.locator('#action-confirm')).to_be_hidden()
                checks.append('Mobile layout, scrolling, triage digest and cancel controls')
                assert not errors, errors
                assert not external, external
                assert page.request.post(base+'/actions/email-summary', data={}).status == 403
                browser.close()
            report = {'status':'passed', 'sourceHead':os.getenv('SOURCE_HEAD','local'), 'checkout':os.getenv('GITHUB_SHA','local'), 'checks':checks, 'screenshots':sorted(p.name for p in output.glob('*.png')), 'externalRequests':external}
            (output/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
            print(json.dumps(report, indent=2))
        except Exception:
            print((Path(tmp)/'server.log').read_text(errors='replace')[-6000:], file=sys.stderr)
            raise
        finally:
            terminate_process(server)


if __name__ == '__main__':
    main()

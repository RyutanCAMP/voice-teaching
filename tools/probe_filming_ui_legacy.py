"""Run unchanged legacy four-step checks and forced opening; no live API."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from tools import e2e_browser as legacy
from voice_teaching import claude_explain as cx
from voice_teaching.claude_interpreter import MockInterpreter
from voice_teaching.web.server import make_server


def run(out):
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    with tempfile.TemporaryDirectory() as folder:
        cfg=legacy.write_test_updown(Path(folder))
        srv=make_server(port=0,interpreter=MockInterpreter(),updown_config=cfg['DEMO_C_PLACE.JBI'],explainer=cx.Explainer(''))
        threading.Thread(target=srv.serve_forever,daemon=True).start()
        url=f'http://127.0.0.1:{srv.server_address[1]}/'
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='chrome',headless=True)
                page=browser.new_page(viewport={'width':1920,'height':1080},reduced_motion='no-preference')
                page.goto(url+'?opening=1')
                start=time.perf_counter()
                page.locator('#opening').wait_for(state='visible')
                page.screenshot(path=str(out/'opening-forced.png'))
                page.locator('#opening').wait_for(state='hidden',timeout=12000)
                page.screenshot(path=str(out/'start-after-opening.png'))
                opening=dict(shown=True,finished=True,seconds=round(time.perf_counter()-start,3),api_calls=0)
                page.close()
                legacy.check_four_steps(browser,url,lambda ok,text:rows.append({'passed':bool(ok),'name':text}),None)
                browser.close()
        finally:
            srv.shutdown();srv.server_close()
    result=dict(api_calls=0,condition='legacy UI checks unchanged; mock interpretation; fictional updown configuration',opening=opening,checks=rows)
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':sum(x['passed'] for x in rows),'failed':sum(not x['passed'] for x in rows),'opening':opening}))
    return 0 if all(x['passed'] for x in rows) else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    raise SystemExit(run(parser.parse_args().out))

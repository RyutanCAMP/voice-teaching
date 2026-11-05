"""ラッパー：chromium.launch の channel 指定を外して、同梱 Chromium で対象スクリプトを動かす（対象ファイルは変更しない）"""
import sys, runpy
from playwright.sync_api._generated import BrowserType
_orig = BrowserType.launch
def launch(self, *a, **k):
    k.pop("channel", None)
    return _orig(self, *a, **k)
BrowserType.launch = launch
target = sys.argv[1]; sys.argv = sys.argv[1:]
runpy.run_path(target, run_name="__main__")

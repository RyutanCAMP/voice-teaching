"""承認済みで、ためらい・否定・疑いの言い方のあとに承認が残って出力できるものを探す（モック・API 0回）。"""
import sys, json, tempfile
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve(); sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
sys.stdout.reconfigure(encoding="utf-8")
import test_claude_talk as T
from voice_teaching import sim
RJ = (ROOT / "samples/dummy/DEMO_RJ_XYZ.JBI").read_bytes()
W = """どうしよう|どうしようかな|迷う|迷うな|悩む|悩むなあ|微妙|微妙かも|うーむ|んー|んーー|うーん、どうかな|どうかな|どうだろう|どうだろ|自信ない|わからん|分からない|よく分からない|心配|不安|怖い|こわい|ちょっと怖い|危なくない？|危ない|危険|やばい|やばくない？|まずい|まずくない？|おかしい|変|変だな|変じゃない？|これでいい？|これでいいのかな|本当にいいの？|いいのかな|大丈夫かな|大丈夫だよね？|ほんまに？|マジで？|うそ|嘘でしょ|待てよ|待てよ、|あ、待って|ストップ|一旦ストップ|とりあえず止めて|保留|保留で|保留にして|考えさせて|ちょっと考える|後で|あとで|また今度|今はいい|今はやめとく|やっぱいい|やっぱりいい|いいや|もういい|もういいや|結構です|けっこうです|いらないです|要らない|不要|NG|ng|×|バツ|ペケ|あかんやろ|あかんて|あかんわ|だめだめ|だめだよ|ダメだね|だめかも|ノーで|ノーです|NOで|nope|no thanks|stop|wait|cancel it|no way|違うかも|違う気がする|なんか違う|ちょっと違う|これじゃない|そうじゃないかも|うまくいかない|失敗|失敗した|ミスった|しまった|あっ|あー|ああ|おっと|えっ、5ミリ？|5ミリ？|5ミリって多くない？|多すぎ|大きすぎ|小さすぎ|もっと少なく|ゆっくり|念のため確認|確認したい|確認させて|見直したい|もう一回見せて|もう一度見る|比べたい|比べて""".split("|")
bad = []
for w in W:
    with tempfile.TemporaryDirectory() as d:
        sim.DEFAULT_OUT_DIR = Path(d)/"o"
        wf, _ = T.flow(Path(d), *[T.answer("この位置へ動く動作です。", (24,)) for _ in range(6)])
        sid = wf.load(RJ)["session_id"]; wf.select(sid, "C00004"); wf.talk(sid, "Zプラス方向に5ミリ", "voice")
        g = wf.candidate_gen_of(sid); wf.approve(sid, "QA", candidate_gen=g)
        r = wf.talk(sid, w, "voice"); s = wf.state(sid)["state"]
        if s.get("approval") and s.get("can_export") and not s.get("hold"):
            bad.append(w)
print(len(bad), "/", len(W), "承認が残って出力できる:", " | ".join(bad))

"""音声テストシート（docs/nl_dialog_check/VOICE_TEST_SHEET_20261106.md）の20ケース＋読み直し1ケースを、モックで流して今の動きを見る。

偽の Claude・MockInterpreter だけ。実 Claude・実マイクは使わない。承認・出力は呼ばない。
実行：python tools/nl_dialog_check/run_voice_sheet.py
"""
import sys, tempfile
from pathlib import Path
root=str(Path(__file__).resolve().parents[2]); sys.path[:0]=[root, root+'/tests']
import test_claude_talk as T
from voice_teaching import jbi, updown
BR=T.demo_bytes(); CP=(Path(root)/'samples/dummy/DEMO_C_PLACE.JBI').read_bytes()
BL=(21,22,23,24,25,26)
ex=lambda t="同じ動きをくり返しています。"+T.ASKED: T.answer(t,BL)
cnt=lambda to=3: T.answer("回数のご希望ですね。",BL,"change_request",{"kind":"repeat","from_count":2,"to_count":to})
C=[
("T01",BR,None,False,["これ、何の作業してるの？"],[ex()]),
("T02",BR,None,False,["動きの流れをざっくり教えて"],[ex("最初の位置へ動いたあと、同じ動きをくり返し、最後に別の位置へ移って終わります。")]),
("T03",CP,"C00003",False,["Yに10ミリ動かして","マイナスね"],[]),
("T04",CP,"C00003",False,["Y方向に10ミリずらして","マイナスの方"],[]),
("T05",CP,"C00003",False,["この点を10ミリ動かしたい","Yマイナス"],[]),
("T06",CP,"C00003",False,["10ミリお願い","Yのマイナス"],[]),
("T07",CP,"C00003",False,["上に3ミリ","Zプラス3ミリ"],[]),
("T08",CP,"C00003",False,["ちょっと手前に寄せて"],[]),
("T09",CP,"C00003",False,["Yのマイナス方向に10ミリ"],[]),
("T10",CP,"C00003",False,["Y軸をマイナスに10ミリ"],[]),
("T11",BR,None,False,["押すのを3回にしてほしい"],[cnt()]),
("T12",BR,None,False,["もう1回だけ増やせる？"],[cnt()]),
("T13",BR,"R3",False,["やっぱり違うな"],[ex()]),
("T14",BR,"R3",False,["それ取り消しといて"],[ex()]),
("T15",BR,"R3",False,["今のはなしにして、動きをもう一回説明して"],[ex()]),
("T16",CP,"C00003",False,["Yに10ミリ","ところでこれ何の作業？","マイナス"],[ex("物を置く作業に見えます。")]),
("T17",BR,"R3",False,["C00003はどこ？"],[ex("押す動きの途中の位置です。")]),
("T18",CP,"C00003",False,["ぜっとマイナス3みり"],[]),
("T19",CP,"C00003",False,["Yマイナス10ミリ出"],[]),
("T20",CP,"C00003",False,["いい感じに直しといて"],[ex("どのように変えたいか教えてください。")]),
("T21",CP,"C00003",False,["Zマイナス3ミリ","@reload"],[]),
]
for cid,job,sel,ud,turns,fake in C:
    tmp=Path(tempfile.mkdtemp()); w,f=T.flow(tmp,*fake); sid=w.load(job)['session_id']
    if sel=="R3": T.repeat_to_three(w,sid)
    elif sel: w.select(sid,sel)
    out=[]
    for t in turns:
        if t=="@reload":
            sid=w.load(job,previous=sid)['session_id']; st=w.state(sid)['state']; out.append(f"[読み直し] cand={bool(st['candidate'])}"); continue
        r=w.talk(sid,t); st=r['state']; c=st.get('candidate')
        m=((r.get('ask') or {}).get('reply') or '')+' '+' '.join((r.get('ask') or {}).get('notes') or [])+' '+((r.get('hear') or {}).get('message') or '')
        out.append(f"{t} → via={r.get('via')} cand={(c.get('target') if c else None)} appr={st.get('can_approve')} range={bool(st.get('repeat_range'))} | {m.strip()[:120]}")
    print(cid,' || '.join(out),'| api',len(f.requests))

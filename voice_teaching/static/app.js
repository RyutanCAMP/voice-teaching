import * as THREE from '/vendor/three.module.js';
import { OrbitControls } from '/vendor/OrbitControls.js';

const $ = id => document.getElementById(id);
let session, state, selected = null, frozen = null, busy = false, playing = false, progress = 0;
let scene, camera, renderer, controls, group, cursor, candidateCursor, labels = [], viewOK = false;
let span = 600, frame, currentMove = null;
const safeText = (tag, text, cls) => {const n = document.createElement(tag); n.textContent = text; if(cls) n.className = cls; return n;};

async function api(path, data) {
  if(busy) throw new Error('処理中です。完了までお待ちください。');
  busy = true; updateButtons();
  try {
    const response = await fetch('/api/' + path, {method:'POST', headers:{'Content-Type':'application/json', 'X-Session':session}, body:JSON.stringify(data)});
    const result = await response.json();
    if(result.state) {state = result.state; render();}
    if(!response.ok) throw new Error(result.error || '処理を完了できませんでした。');
    $('error').hidden = true;
    return result;
  } finally {busy = false; updateButtons();}
}
function report(error) {$('error').textContent = error.message || '処理を完了できませんでした。'; $('error').hidden = false;}
function action(fn) {return (...args) => Promise.resolve().then(()=>fn(...args)).catch(report);}
function updateButtons() {
  for(const el of document.querySelectorAll('button,input[type=file],select,textarea')) el.disabled = busy;
  const loaded = Boolean(state?.current?.positions && Object.keys(state.current.positions).length);
  $('utterance').disabled = busy || !loaded;
  $('interpret').disabled = busy || !loaded || !$('utterance').value.trim();
  $('microphone').disabled = true;
  for(const id of ['play','step','reset','seek']) $(id).disabled = busy || !viewOK || !state?.current?.playable;
  $('approve').disabled = busy || !state?.candidate;
}
function resetInput() {frozen = null; $('utterance').value = ''; $('frozen').textContent = '入力対象：未選択';}
function selectPosition(name) {
  selected = name;
  $('selected').textContent = name;
  document.querySelectorAll('.point').forEach(b=>b.classList.toggle('selected', b.dataset.position===name));
  labels.forEach(l=>l.element.classList.toggle('selected', l.name===name));
}
function render() {
  playing = false; progress = 0; currentMove = null;
  const view = state.current;
  $('job-name').textContent = view ? (view.name || '名称不明のJBI') : '未読込';
  $('baseline').textContent = view ? state.baseline_hash : '—';
  $('policy-status').textContent = state.policy ? 'プレビュー用の枠を読込済み。実機用には使えません。' : '未設定：変更案は作りません。左右の軸・向き・上限を自動で決めません。';
  $('model-status').textContent = state.robot_model;
  $('positions').replaceChildren();
  for(const [name, xyz] of Object.entries(view?.positions || {})) {
    const b = safeText('button','', 'point'); b.dataset.position = name;
    b.append(safeText('b',name), safeText('small', xyz.map(v=>v.toFixed(3)).join(' / ')));
    b.onclick = ()=>selectPosition(name); $('positions').append(b);
  }
  if(!Object.keys(view?.positions || {}).length) $('positions').append(safeText('p','描画できる位置がありません。','empty'));
  if(!view?.positions[selected]) selected = Object.keys(view?.positions || {})[0] || null;
  $('selected').textContent = selected || '位置を選択してください';
  $('issues').replaceChildren(...(view?.issues || []).map(t=>safeText('p',t)));
  $('instructions').replaceChildren(...(view?.instructions || []).map(i=>{
    const div = safeText('div','', 'instruction'); div.dataset.line = i.line;
    div.append(safeText('span',String(i.line)), safeText('b',i.text)); return div;
  }));
  const c = state.candidate;
  $('candidate').hidden = !c; $('comparison-empty').hidden = Boolean(c);
  if(c) {
    $('numbers').replaceChildren(...['X','Y','Z'].map((axis,i)=>safeText('span',`${axis}  ${c.before[i].toFixed(3)} → ${c.after[i].toFixed(3)}`)));
    $('diff').textContent = '− ' + c.diff.before + '\n＋ ' + c.diff.after;
    $('confirmation').textContent = c.confirmation;
  }
  $('approved-status').textContent = state.history.length ? `プレビュー内で承認済み：${state.history.length}件。ファイル出力はしていません。` : '';
  buildScene(); selectPosition(selected); updateButtons();
}

function init3D() {
  const host = $('viewport');
  try {
    scene = new THREE.Scene(); scene.background = new THREE.Color('#f2f6fc');
    camera = new THREE.PerspectiveCamera(42,1,1,100000); camera.up.set(0,0,1);
    renderer = new THREE.WebGLRenderer({antialias:true}); renderer.setPixelRatio(Math.min(devicePixelRatio,2));
    host.prepend(renderer.domElement);
    controls = new OrbitControls(camera,renderer.domElement); controls.enableDamping = true;
    group = new THREE.Group(); scene.add(group);
    new ResizeObserver(()=>{const w=host.clientWidth,h=host.clientHeight; renderer.setSize(w,h); camera.aspect=w/h; camera.updateProjectionMatrix();}).observe(host);
    viewOK = true;
    requestAnimationFrame(tick);
  } catch(_) {
    $('placeholder').textContent = '3D描画を開始できません。位置表と差分で確認してください。';
    viewOK = false;
  }
}
function v(xyz) {return new THREE.Vector3(...xyz);}
function clearScene() {
  for(const child of [...group.children]) {
    child.traverse(n=>{n.geometry?.dispose(); if(n.material) {const ms=Array.isArray(n.material)?n.material:[n.material]; ms.forEach(m=>m.dispose());}});
    group.remove(child);
  }
  labels.forEach(l=>l.element.remove()); labels=[];
}
function pathFor(view, color) {
  if(!view?.playable) return;
  const points=view.moves.map(m=>v(view.positions[m.position]));
  const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({color})); group.add(line);
}
function buildScene() {
  if(!viewOK) return;
  clearScene(); cursor=null; candidateCursor=null;
  const view = state.current, points = Object.values(view?.positions || {});
  $('placeholder').hidden = Boolean(points.length);
  if(!points.length) return;
  const box = new THREE.Box3().setFromPoints(points.map(v));
  if(state.candidate) for(const p of Object.values(state.candidate.view.positions)) box.expandByPoint(v(p));
  span = Math.max(...box.getSize(new THREE.Vector3()).toArray(),100);
  const grid = new THREE.GridHelper(span*2,20,0xb7c6d9,0xdde5ef); grid.rotation.x=Math.PI/2;
  const center=box.getCenter(new THREE.Vector3()); grid.position.set(center.x,center.y,0); group.add(grid);
  group.add(new THREE.AxesHelper(span*.4));
  pathFor(view, 0x9baec7); pathFor(state.candidate?.view,0x2464ce);
  const radius=span*.012;
  for(const [name,xyz] of Object.entries(view.positions)) {
    const dot=new THREE.Mesh(new THREE.SphereGeometry(radius,14,10),new THREE.MeshBasicMaterial({color:0x718ba9}));
    dot.position.copy(v(xyz)); group.add(dot);
    const element=safeText('span',name,'label'); $('labels').append(element); labels.push({name,xyz,element});
  }
  if(state.candidate) {
    const dot=new THREE.Mesh(new THREE.SphereGeometry(radius*1.2,14,10),new THREE.MeshBasicMaterial({color:0x2464ce}));
    dot.position.copy(v(state.candidate.after)); group.add(dot);
  }
  cursor=new THREE.Mesh(new THREE.SphereGeometry(radius*1.35,16,10),new THREE.MeshBasicMaterial({color:0xecac32}));group.add(cursor);
  candidateCursor=new THREE.Mesh(new THREE.SphereGeometry(radius*1.1,16,10),new THREE.MeshBasicMaterial({color:0x2464ce}));group.add(candidateCursor);
  resetCamera();
}
function resetCamera() {
  if(!viewOK || !state?.current) return;
  const points=Object.values(state.current.positions);
  if(!points.length) return;
  const center=new THREE.Box3().setFromPoints(points.map(v)).getCenter(new THREE.Vector3());
  controls.target.copy(center); camera.position.copy(center).add(new THREE.Vector3(span*1.55,-span*1.8,span*1.25)); controls.update();
}
function at(view,p) {
  if(!view?.playable) return null;
  const t=p*(view.moves.length-1),i=Math.min(Math.floor(t),view.moves.length-2),alpha=t-i;
  return {xyz:v(view.positions[view.moves[i].position]).lerp(v(view.positions[view.moves[i+1].position]),alpha),move:view.moves[i+1]};
}
let last=0;
function tick(now) {
  const dt=Math.min((now-last)/1000,.1);last=now;
  if(playing && state?.current?.playable) {progress=Math.min(1,progress+dt/Math.max(1,(state.current.moves.length-1)*1.5)); if(progress===1) playing=false;}
  if(cursor && state?.current) {
    const a=at(state.current,progress), b=at(state.candidate?.view,progress);
    cursor.visible=Boolean(a); candidateCursor.visible=Boolean(b);
    if(a) {
      cursor.position.copy(a.xyz); $('active-point').textContent=a.move.position+' / '+a.move.line+'行';
      if(a.move.line!==currentMove) {currentMove=a.move.line;document.querySelectorAll('.instruction').forEach(el=>el.classList.toggle('active',+el.dataset.line===currentMove));}
    }
    if(b) candidateCursor.position.copy(b.xyz);
  }
  controls.update();renderer.render(scene,camera);
  for(const l of labels) {
    const p=v(l.xyz).project(camera),w=$('viewport').clientWidth,h=$('viewport').clientHeight;
    l.element.hidden=p.z < -1 || p.z > 1 || Math.abs(p.x)>1 || Math.abs(p.y)>1;
    l.element.style.transform=`translate(${(p.x+1)*w/2+8}px,${(1-p.y)*h/2-16}px)`;
  }
  $('seek').value=progress; $('play').textContent=playing?'一時停止':'再生';
  frame=requestAnimationFrame(tick);
}

$('dummy').onclick=action(async()=>{resetInput();await api('load',{dummy:true});});
$('file').onchange=action(async(e)=>{
  const file=e.target.files[0];if(!file)return;
  resetInput();
  await api('clear',{});
  if(file.size>2_000_000) throw new Error('ファイルは2MB以下で指定してください。');
  let bytes;
  busy=true;updateButtons();
  try {bytes=new Uint8Array(await file.arrayBuffer());}
  finally {busy=false;updateButtons();}
  let binary='';for(const n of bytes) binary+=String.fromCharCode(n);
  await api('load',{bytes:btoa(binary),encoding:$('encoding').value});
});
$('policy').onchange=action(async(e)=>{
  const file=e.target.files[0];if(!file)return;
  await api('invalidate',{});
  try {await api('policy',{policy:JSON.parse(await file.text())});} catch(error) {await api('policy',{policy:null});throw error;}
});
$('utterance').onfocus=()=>{if(!frozen && selected) {frozen=selected;$('frozen').textContent='入力対象（固定）：'+frozen;}};
$('utterance').oninput=action(async()=>{if(state.candidate) await api('invalidate',{});updateButtons();});
$('interpret').onclick=action(async()=>{
  playing=false;
  const target=frozen || selected, text=$('utterance').value;
  const start=await api('begin',{selected:target});
  await api('propose',{input_token:start.input_token,text});
});
$('approve').onclick=action(async()=>{const id=state.candidate?.id;await api('approve',{candidate_id:id});resetInput();});
$('cancel').onclick=action(async()=>{await api('invalidate',{});resetInput();});
$('play').onclick=()=>{if(progress===1)progress=0;playing=!playing;};
$('reset').onclick=()=>{playing=false;progress=0;};
$('step').onclick=()=>{playing=false;const n=state.current.moves.length-1;progress=Math.min(1,(Math.floor(progress*n+1e-7)+1)/n);};
$('seek').oninput=e=>{playing=false;progress=+e.target.value;};
$('camera').onclick=resetCamera;

try {
  const response=await fetch('/api/bootstrap');if(!response.ok)throw new Error('ローカルサーバーに接続できません。');
  const initial=await response.json();session=initial.session;state=initial.state;
  $('api-status').textContent=initial.claude_configured?'Claude API 設定済み · 接続未確認':'Claude API 未設定';
  init3D();render();
} catch(error) {report(error);}

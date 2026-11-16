import os, sqlite3, secrets, hmac, time, datetime as dt, functools
from flask import Flask, request, redirect, session, render_template_string, jsonify, abort

app=Flask(__name__)
app.secret_key=os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE')=='1',PERMANENT_SESSION_LIFETIME=dt.timedelta(days=30))
DB=os.environ.get('DATABASE_PATH','volym.sqlite3')
PIN=os.environ.get('APP_PIN')
ATTEMPTS={}
DAYS=['Måndag','Tisdag','Onsdag','Torsdag','Fredag','Lördag','Söndag']
WORKOUTS={
0:('Push – bröst, axlar, triceps',[('Lutande hantelpress',3,'6–10'),('Bröstpress i maskin',3,'8–12'),('Sidolyft i kabel',3,'12–20'),('Pec deck',2,'10–15'),('Triceps pushdown',3,'10–15'),('Triceps över huvudet i kabel',2,'10–15')]),
1:('Pull – rygg, biceps',[('Latsdrag',3,'8–12'),('Bröststödd rodd',3,'8–12'),('Enarms latsdrag i kabel',2,'10–15'),('Omvänd pec deck',3,'12–20'),('Preachercurl',3,'8–12'),('Hammercurl',2,'10–15')]),
2:('Ben och mage',[('Hack squat / benpress',3,'8–12'),('Rumänska marklyft',3,'8–12'),('Benspark',2,'10–15'),('Sittande lårcurl',3,'10–15'),('Vadpress',3,'10–20'),('Cable crunch',3,'10–15')]),
4:('Överkropp – bredd och volym',[('Lutande bröstpress',3,'8–12'),('Latsdrag neutralt grepp',3,'8–12'),('Sittande kabelrodd',2,'8–12'),('Sidolyft i kabel',3,'12–20'),('Cable flyes',2,'10–15'),('Bicepscurl i kabel',2,'10–15'),('Triceps pushdown',2,'10–15')]),
5:('Axlar, armar och extra ben',[('Axelpress i maskin',2,'8–12'),('Sidolyft med hantlar',3,'12–20'),('Omvänd pec deck',2,'12–20'),('EZ-curl',3,'8–12'),('Triceps över huvudet i kabel',3,'10–15'),('Benpress',2,'10–15'),('Lårcurl',2,'10–15')])}
def conn():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c
def init():
 with conn() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS workouts(id INTEGER PRIMARY KEY,date TEXT NOT NULL,title TEXT NOT NULL,done INTEGER NOT NULL DEFAULT 0,notes TEXT DEFAULT '');CREATE TABLE IF NOT EXISTS sets(id INTEGER PRIMARY KEY,workout_id INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,exercise TEXT NOT NULL,set_number INTEGER NOT NULL,kg REAL NOT NULL,reps INTEGER NOT NULL,rir INTEGER,UNIQUE(workout_id,exercise,set_number));CREATE TABLE IF NOT EXISTS weights(date TEXT PRIMARY KEY,kg REAL NOT NULL);CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);''')
  c.execute('PRAGMA foreign_keys=ON')
init()
def auth(f):
 @functools.wraps(f)
 def inner(*a,**kw):
  if not session.get('ok'):return redirect('/login') if request.method=='GET' else (jsonify(error='Logga in igen'),401)
  return f(*a,**kw)
 return inner
@app.before_request
def protect():
 if request.method in ('POST','PUT','DELETE') and request.path!='/login':
  if not session.get('ok'):return jsonify(error='Ej inloggad'),401
  if not hmac.compare_digest(request.headers.get('X-CSRF',''),session.get('csrf','missing')):return jsonify(error='Ogiltig säkerhetstoken'),403
@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  ip=request.remote_addr or 'unknown'; now=time.monotonic();attempts=[t for t in ATTEMPTS.get(ip,[]) if now-t<900];ATTEMPTS[ip]=attempts
  if len(attempts)>=5:return render_template_string(LOGIN,error='För många försök. Försök igen om 15 minuter.'),429
  entered=request.form.get('pin','');ATTEMPTS[ip].append(now)
  if PIN and hmac.compare_digest(entered,PIN):
   ATTEMPTS.pop(ip,None);session.clear();session['ok']=True;session['csrf']=secrets.token_urlsafe(32);session.permanent=True;return redirect('/')
  return render_template_string(LOGIN,error='Fel kod.'),401
 return render_template_string(LOGIN,error=None)
@app.get('/logout')
def logout():session.clear();return redirect('/login')
@app.get('/')
@auth
def home():return render_template_string(PAGE,csrf=session['csrf'],today=dt.date.today().isoformat())
def payload():return request.get_json(force=True)
@app.get('/api/state')
@auth
def state():
 with conn() as c:
  return jsonify(workouts=[dict(x) for x in c.execute('SELECT * FROM workouts ORDER BY date DESC,id DESC')],sets=[dict(x) for x in c.execute('SELECT * FROM sets ORDER BY set_number')],weights=[dict(x) for x in c.execute('SELECT * FROM weights ORDER BY date')],settings={x['key']:x['value'] for x in c.execute('SELECT * FROM settings')},templates={str(k):{'title':v[0],'exercises':v[1]} for k,v in WORKOUTS.items()})
@app.post('/api/workout')
@auth
def workout():
 p=payload();date=dt.date.fromisoformat(p['date']);title=str(p.get('title') or WORKOUTS.get(date.weekday(),('Eget pass',))[0])[:100]
 with conn() as c:cur=c.execute('INSERT INTO workouts(date,title) VALUES(?,?)',(date.isoformat(),title));return jsonify(id=cur.lastrowid)
@app.post('/api/workout/<int:id>')
@auth
def update_workout(id):
 p=payload();fields=[];vals=[]
 if 'done' in p:fields.append('done=?');vals.append(int(bool(p['done'])))
 if 'notes' in p:fields.append('notes=?');vals.append(str(p['notes'])[:2000])
 if 'date' in p:fields.append('date=?');vals.append(dt.date.fromisoformat(p['date']).isoformat())
 if not fields:abort(400)
 with conn() as c:c.execute('UPDATE workouts SET '+','.join(fields)+' WHERE id=?',(*vals,id))
 return jsonify(ok=True)
@app.delete('/api/workout/<int:id>')
@auth
def delete_workout(id):
 with conn() as c:c.execute('DELETE FROM sets WHERE workout_id=?',(id,));c.execute('DELETE FROM workouts WHERE id=?',(id,))
 return jsonify(ok=True)
@app.post('/api/set')
@auth
def setlog():
 p=payload();kg=float(p['kg']);reps=int(p['reps']);rir=None if p.get('rir') in (None,'') else int(p['rir']);wid=int(p['workout_id']);number=int(p['set_number']);exercise=str(p['exercise'])[:100]
 if not (0<=kg<=1000 and 0<=reps<=200 and 1<=number<=20 and (rir is None or 0<=rir<=10)):abort(400)
 with conn() as c:
  if not c.execute('SELECT id FROM workouts WHERE id=?',(wid,)).fetchone():abort(404)
  c.execute('INSERT INTO sets(workout_id,exercise,set_number,kg,reps,rir) VALUES(?,?,?,?,?,?) ON CONFLICT(workout_id,exercise,set_number) DO UPDATE SET kg=excluded.kg,reps=excluded.reps,rir=excluded.rir',(wid,exercise,number,kg,reps,rir))
 return jsonify(ok=True)
@app.delete('/api/set/<int:id>')
@auth
def delete_set(id):
 with conn() as c:c.execute('DELETE FROM sets WHERE id=?',(id,))
 return jsonify(ok=True)
@app.post('/api/weight')
@auth
def weight():
 p=payload();date=dt.date.fromisoformat(p['date']);kg=float(p['kg'])
 if not 20<=kg<=400:abort(400)
 with conn() as c:c.execute('INSERT INTO weights(date,kg) VALUES(?,?) ON CONFLICT(date) DO UPDATE SET kg=excluded.kg',(date.isoformat(),kg))
 return jsonify(ok=True)
@app.delete('/api/weight/<date>')
@auth
def delete_weight(date):
 dt.date.fromisoformat(date)
 with conn() as c:c.execute('DELETE FROM weights WHERE date=?',(date,))
 return jsonify(ok=True)
@app.post('/api/settings')
@auth
def settings():
 p=payload();allowed={'start_date','calories','protein','fat','carbs'}
 with conn() as c:
  for k,v in p.items():
   if k not in allowed:continue
   if k=='start_date':v=dt.date.fromisoformat(v).isoformat()
   else:
    v=float(v)
    if not 0<=v<=10000:abort(400)
   c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,str(v)))
 return jsonify(ok=True)
LOGIN='''<!doctype html><html lang="sv"><meta name="viewport" content="width=device-width,initial-scale=1"><meta charset="utf-8"><title>Volym · Logga in</title><style>body{background:#0b1016;color:#f4f6fa;font:16px system-ui;display:grid;place-items:center;min-height:95vh}main{background:#161e29;padding:35px;border-radius:22px;width:min(320px,85vw)}input,button{box-sizing:border-box;width:100%;padding:15px;border-radius:10px;border:1px solid #394457;background:#0c121a;color:white;font-size:18px;margin:8px 0}button{background:#c2f277;color:#17200d;border:0;font-weight:800;cursor:pointer}.error{color:#ff9797}</style><main><h1>VOLYM.</h1><p>Din personliga träningslogg</p><form method="post"><input name="pin" type="password" inputmode="numeric" placeholder="Ange PIN" required autofocus><button>Öppna appen</button></form>{% if error %}<p class="error">{{error}}</p>{% endif %}</main></html>'''
PAGE='''<!doctype html><html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Volym – Träningslogg</title><script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script><style>
:root{font-family:Inter,system-ui,-apple-system,sans-serif;color:#edf2f6;background:#0b1016}*{box-sizing:border-box}body{margin:0}header{border-bottom:1px solid #27313e;padding:18px max(18px,calc((100vw - 1080px)/2));display:flex;align-items:center;justify-content:space-between}.brand{font-size:25px;font-weight:900;letter-spacing:-1px}.brand span{color:#c2f277}a{color:#a9d7ff}main{max-width:1080px;margin:auto;padding:24px 18px 80px}.muted{color:#94a3b8}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.card{background:#161f2a;border:1px solid #293544;border-radius:18px;padding:20px;margin:12px 0}.metric{font-size:30px;font-weight:850}.green{color:#c2f277}nav{display:flex;gap:7px;overflow-x:auto;padding:12px 18px;max-width:1116px;margin:auto}button{background:#c2f277;color:#101710;border:0;border-radius:10px;padding:11px 15px;font-weight:750;cursor:pointer}button.secondary,nav button{background:#1b2633;color:#e9f0f8}nav button.active{background:#c2f277;color:#17200b}button.danger{background:#40242b;color:#ffb9c1}input,select,textarea{background:#0e151e;color:#f3f5f8;border:1px solid #3b4a5b;border-radius:9px;padding:10px;font:inherit;min-width:0}input[type=number]{width:100px}input[type=date]{width:155px}h1{font-size:30px;margin:8px 0}h2{font-size:20px}h3{font-size:16px}p{line-height:1.5}.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.spread{justify-content:space-between}.exercise{border-top:1px solid #2d3948;padding:15px 0}.setrow{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:8px 0}.setrow input{width:75px}.tag{font-size:12px;background:#263547;padding:5px 9px;border-radius:20px}.hidden{display:none}.calendar{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:7px}.day{min-height:88px;background:#111924;border:1px solid #303c4b;border-radius:10px;padding:8px;cursor:pointer}.day.selected{border-color:#c2f277}.day .num{font-weight:800}.dot{color:#c2f277;font-size:11px}canvas{max-height:300px}.small{font-size:13px}.week{font-size:12px;color:#93a2b6}@media(max-width:680px){.grid{grid-template-columns:1fr 1fr}.card{padding:14px}.metric{font-size:23px}.day{padding:4px;min-height:64px;font-size:11px}.day .dot{font-size:9px}.setrow input{width:62px}header{padding:14px 18px}}
</style></head><body><header><div class="brand">VOLYM<span>.</span></div><div class="small muted">12 veckor · Bygg muskler &nbsp; <a href="/logout">Logga ut</a></div></header><nav id="nav"><button data-tab="overview" class="active">Översikt</button><button data-tab="calendar">Kalender</button><button data-tab="training">Träningslogg</button><button data-tab="weight">Kroppsvikt</button><button data-tab="history">Historik</button><button data-tab="settings">Inställningar</button></nav><main><div id="content"></div></main><script>
const CSRF={{csrf|tojson}},TODAY={{today|tojson}};let state={},tab='overview',selectedDate=TODAY,selectedWorkout=null,month=TODAY.slice(0,7),charts=[];
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=d=>new Date(d+'T12:00:00').toLocaleDateString('sv-SE',{day:'numeric',month:'short',year:'numeric'});const weekday=d=>(new Date(d+'T12:00:00').getDay()+6)%7;
async function api(url,method='GET',data){const r=await fetch(url,{method,headers:{'Content-Type':'application/json','X-CSRF':CSRF},body:data===undefined?undefined:JSON.stringify(data)});if(!r.ok){alert('Kunde inte spara: '+(await r.text()).slice(0,130));throw Error('API error')}return r.json()}
async function refresh(){state=await api('/api/state');render()}
function switchTab(t){tab=t;document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.tab===t));render()}
$('#nav').addEventListener('click',e=>{if(e.target.dataset.tab)switchTab(e.target.dataset.tab)});
function target(){return {calories:state.settings.calories||2900,protein:state.settings.protein||150,fat:state.settings.fat||80,carbs:state.settings.carbs||395}}
function overview(){let completed=state.workouts.filter(w=>w.done),latest=state.weights.at(-1),start=state.settings.start_date||TODAY;let weeks=Math.max(1,Math.min(12,Math.floor((new Date(TODAY)-new Date(start))/604800000)+1));return `<h1>Din utveckling</h1><p class="muted">Vecka ${weeks} av 12 · 183 cm · Start 74 kg · Mål 77–78 kg</p><div class="grid"><div class="card"><div class="muted small">Nuvarande vikt</div><div class="metric">${latest?latest.kg.toLocaleString('sv-SE'):'74'} <small>kg</small></div></div><div class="card"><div class="muted small">Genomförda pass</div><div class="metric green">${completed.length}</div></div><div class="card"><div class="muted small">Loggade set</div><div class="metric">${state.sets.length}</div></div></div><div class="card"><h2>Dagens pass</h2>${todayCard(TODAY)}</div><div class="card"><h2>Dagliga kostmål</h2><div class="grid">${Object.entries(target()).map(([k,v])=>`<div><div class="metric">${v}</div><div class="muted small">${({calories:'kcal',protein:'g protein',fat:'g fett',carbs:'g kolhydrater'})[k]}</div></div>`).join('')}</div></div><div class="card"><h2>Viktutveckling</h2><canvas id="weightchart"></canvas></div>`}
function todayCard(date){let d=weekday(date),template=state.templates[d],done=state.workouts.filter(w=>w.date===date);return `<p class="muted">${fmt(date)}</p><h2>${esc(template?.title||'Vilodag')}</h2><p>${done.length?done.map(w=>`<span class="tag">${w.done?'✓ Genomfört':'Påbörjat'}: ${esc(w.title)}</span>`).join(' '):'Inget pass loggat ännu'}</p><button onclick="selectedDate='${date}';switchTab('training')">${template?'Öppna passet':'Visa träningslogg'}</button>`}
function calendar(){let [y,m]=month.split('-').map(Number),first=new Date(y,m-1,1),days=new Date(y,m,0).getDate(),offset=(first.getDay()+6)%7;let cells=Array.from({length:offset},()=>'<div></div>');for(let d=1;d<=days;d++){let date=`${y}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`,ws=state.workouts.filter(w=>w.date===date),tpl=state.templates[weekday(date)];cells.push(`<div class="day ${selectedDate===date?'selected':''}" onclick="selectedDate='${date}';render()"><div class="num">${d}</div><div class="dot">${ws.some(w=>w.done)?'✓ Klart':ws.length?'● Påbörjat':tpl?'• '+['Push','Pull','Ben','','Överkropp','Axlar'][weekday(date)]:''}</div></div>`)}return `<h1>Träningskalender</h1><div class="row spread"><button class="secondary" onclick="moveMonth(-1)">←</button><h2>${first.toLocaleDateString('sv-SE',{month:'long',year:'numeric'})}</h2><button class="secondary" onclick="moveMonth(1)">→</button></div><div class="calendar">${['Mån','Tis','Ons','Tor','Fre','Lör','Sön'].map(x=>`<div class="week">${x}</div>`).join('')}${cells.join('')}</div><div class="card">${todayCard(selectedDate)}</div>`}
function moveMonth(delta){let [y,m]=month.split('-').map(Number);month=new Date(y,m-1+delta,1).toISOString().slice(0,7);render()}
function training(){let d=weekday(selectedDate),tpl=state.templates[d],ws=state.workouts.filter(w=>w.date===selectedDate),chosen=ws.find(w=>w.id===selectedWorkout)||ws[0];selectedWorkout=chosen?.id||null;let start=state.settings.start_date||TODAY,week=Math.floor((new Date(selectedDate)-new Date(start))/604800000)+1;return `<h1>Träningslogg</h1><div class="card"><div class="row"><label>Datum <input type="date" value="${selectedDate}" onchange="selectedDate=this.value;selectedWorkout=null;render()"></label><button onclick="createWorkout()">+ Nytt pass</button></div><p class="muted">Planerat: ${esc(tpl?.title||'Vila / valfritt pass')}</p>${ws.length?`<div class="row">${ws.map(w=>`<button class="${w.id===selectedWorkout?'':'secondary'}" onclick="selectedWorkout=${w.id};render()">${esc(w.title)} ${w.done?'✓':''}</button>`).join('')}</div>`:''}</div>${chosen?workoutEditor(chosen,week):'<div class="card muted">Välj ett datum och skapa ett pass för att börja logga.</div>'}`}
function workoutEditor(w,week){let tpl=state.templates[weekday(w.date)],names=tpl?.exercises||[],logged=state.sets.filter(s=>s.workout_id===w.id),all=[...new Set([...names.map(e=>e[0]),...logged.map(s=>s.exercise)])];return `<div class="card"><div class="row spread"><h2>${esc(w.title)}</h2><span class="tag">${w.done?'✓ Genomfört':'Pågående'}</span></div><div class="row"><button onclick="markDone(${w.id},${w.done?0:1})">${w.done?'Markera som pågående':'✓ Markera genomfört'}</button><button class="danger" onclick="deleteWorkout(${w.id})">Radera pass</button></div><p class="small muted">Vecka ${week>0?week:1}: ${week<=2?'börja med 2 arbetsset per övning':'följ rekommenderade arbetsset'}. RIR = repetitioner kvar i tanken.</p>${all.map(name=>{let entry=names.find(e=>e[0]===name),count=week<=2?Math.min(2,entry?.[1]||2):entry?.[1]||2;return `<div class="exercise"><div class="row spread"><strong>${esc(name)}</strong><span class="tag">${count} set · ${entry?.[2]||'valfritt'} reps</span></div>${Array.from({length:Math.max(count,...logged.filter(s=>s.exercise===name).map(s=>s.set_number),0)},(_,i)=>{let n=i+1,s=logged.find(s=>s.exercise===name&&s.set_number===n),prev=state.sets.filter(v=>v.exercise===name&&v.workout_id!==w.id&&state.workouts.find(z=>z.id===v.workout_id)?.date<=w.date).sort((a,b)=>(state.workouts.find(z=>z.id===b.workout_id)?.date||'').localeCompare(state.workouts.find(z=>z.id===a.workout_id)?.date||''))[0];return `<div class="setrow"><span class="muted small">${n}.</span><label class="small">kg <input id="kg-${w.id}-${encodeURIComponent(name)}-${n}" type="number" step="0.5" min="0" value="${s?.kg??prev?.kg??''}"></label><label class="small">reps <input id="reps-${w.id}-${encodeURIComponent(name)}-${n}" type="number" min="0" value="${s?.reps??''}"></label><label class="small">RIR <input id="rir-${w.id}-${encodeURIComponent(name)}-${n}" type="number" min="0" max="10" value="${s?.rir??''}"></label><button onclick="saveSet(${w.id},${JSON.stringify(name).replaceAll('"','&quot;')},${n})">${s?'Uppdatera':'Spara'}</button>${s?`<button class="danger" onclick="deleteSet(${s.id})">×</button>`:''}</div>`}).join('')}</div>`}).join('')}<label class="muted">Anteckningar <textarea id="notes" rows="2" style="width:100%">${esc(w.notes)}</textarea></label><button class="secondary" onclick="saveNotes(${w.id})">Spara anteckningar</button></div>`}
async function createWorkout(){let tpl=state.templates[weekday(selectedDate)],title=prompt('Namn på pass',tpl?.title||'Eget pass');if(!title)return;let r=await api('/api/workout','POST',{date:selectedDate,title});selectedWorkout=r.id;await refresh()}
async function markDone(id,done){await api('/api/workout/'+id,'POST',{done});await refresh()}
async function deleteWorkout(id){if(confirm('Radera passet och alla dess set?')){await api('/api/workout/'+id,'DELETE');selectedWorkout=null;await refresh()}}
async function saveNotes(id){await api('/api/workout/'+id,'POST',{notes:$('#notes').value});await refresh()}
async function saveSet(id,name,n){let suffix=`${id}-${encodeURIComponent(name)}-${n}`,kg=$('#kg-'+suffix).value,reps=$('#reps-'+suffix).value,rir=$('#rir-'+suffix).value;if(kg===''||reps===''){alert('Ange kg och repetitioner');return}await api('/api/set','POST',{workout_id:id,exercise:name,set_number:n,kg:Number(kg),reps:Number(reps),rir:rir===''?null:Number(rir)});await refresh()}
async function deleteSet(id){if(confirm('Radera detta set?')){await api('/api/set/'+id,'DELETE');await refresh()}}
function weight(){let latest=state.weights.at(-1);return `<h1>Kroppsvikt</h1><div class="grid"><div class="card"><div class="muted small">Startvikt</div><div class="metric">74 kg</div></div><div class="card"><div class="muted small">Senaste</div><div class="metric green">${latest?.kg??'–'} kg</div></div><div class="card"><div class="muted small">Mål</div><div class="metric">77–78 kg</div></div></div><div class="card"><h2>Registrera vikt</h2><div class="row"><input id="weightDate" type="date" value="${TODAY}"><input id="weightKg" type="number" min="20" max="400" step="0.1" placeholder="kg"><button onclick="saveWeight()">Spara vikt</button></div></div><div class="card"><h2>Viktkurva</h2><canvas id="weightchart"></canvas></div><div class="card"><h2>Historik</h2>${[...state.weights].reverse().map(w=>`<div class="row spread exercise"><span>${fmt(w.date)} – <strong>${w.kg} kg</strong></span><div><button class="secondary" onclick="editWeight('${w.date}',${w.kg})">Ändra</button> <button class="danger" onclick="deleteWeight('${w.date}')">Radera</button></div></div>`).join('')||'<p class="muted">Inga vägningar ännu.</p>'}</div>`}
async function saveWeight(){let date=$('#weightDate').value,kg=Number($('#weightKg').value);if(!date||!kg)return alert('Ange datum och vikt');await api('/api/weight','POST',{date,kg});await refresh()}
async function editWeight(date,kg){let value=prompt('Ny vikt i kg',kg);if(value!==null&&Number(value)>0){await api('/api/weight','POST',{date,kg:Number(value)});await refresh()}}
async function deleteWeight(date){if(confirm('Radera vägningen?')){await api('/api/weight/'+date,'DELETE');await refresh()}}
function history(){return `<h1>Historik och progression</h1><div class="card"><h2>Genomförda och påbörjade pass</h2>${state.workouts.map(w=>`<div class="exercise row spread"><div><strong>${fmt(w.date)}</strong> · ${esc(w.title)} <span class="tag">${w.done?'✓ Klart':'Påbörjat'}</span><div class="muted small">${state.sets.filter(s=>s.workout_id===w.id).length} loggade set</div></div><button class="secondary" onclick="selectedDate='${w.date}';selectedWorkout=${w.id};switchTab('training')">Visa / ändra</button></div>`).join('')||'<p class="muted">Inga pass loggade ännu.</p>'}</div><div class="card"><h2>Progression per övning</h2><select id="exerciseSelect" onchange="drawExercise()">${[...new Set(state.sets.map(s=>s.exercise))].map(e=>`<option value="${esc(e)}">${esc(e)}</option>`).join('')}</select><canvas id="exercisechart"></canvas></div>`}
function settings(){let t=target();return `<h1>Inställningar</h1><div class="card"><h2>Programstart</h2><p class="muted">Välj datum för vecka 1. De första två veckorna föreslås färre set.</p><input type="date" id="start" value="${state.settings.start_date||TODAY}"></div><div class="card"><h2>Dagliga kostmål</h2><div class="row">${Object.entries(t).map(([k,v])=>`<label>${({calories:'Kalorier',protein:'Protein (g)',fat:'Fett (g)',carbs:'Kolhydrater (g)'})[k]}<br><input id="s-${k}" type="number" value="${v}"></label>`).join('')}</div></div><button onclick="saveSettings()">Spara inställningar</button><div class="card"><h2>Dataskydd</h2><p class="muted">Dina data lagras i appens SQLite-databas. Säkerhetskopiera databasfilen regelbundet. PIN-koden ställs in som miljövariabel på servern. Publicera endast bakom HTTPS.</p></div>`}
async function saveSettings(){await api('/api/settings','POST',{start_date:$('#start').value,...Object.fromEntries(['calories','protein','fat','carbs'].map(k=>[k,Number($('#s-'+k).value)]))});await refresh()}
function drawWeight(){let el=$('#weightchart');if(!el||typeof Chart==='undefined')return;let ws=state.weights,groups={};ws.forEach(w=>{let date=new Date(w.date+'T12:00:00'),day=(date.getDay()+6)%7;date.setDate(date.getDate()-day);let key=date.toISOString().slice(0,10);(groups[key]??=[]).push(w.kg)});charts.push(new Chart(el,{type:'line',data:{labels:Object.keys(groups).map(fmt),datasets:[{label:'Veckomedel (kg)',data:Object.values(groups).map(v=>+(v.reduce((a,b)=>a+b,0)/v.length).toFixed(2)),borderColor:'#c2f277',backgroundColor:'#c2f277',tension:.3}]},options:{responsive:true,plugins:{legend:{labels:{color:'#cbd5e1'}}},scales:{x:{ticks:{color:'#94a3b8'}},y:{ticks:{color:'#94a3b8'}}}}}))}
function drawExercise(){let el=$('#exercisechart'),name=$('#exerciseSelect')?.value;if(!el||!name||typeof Chart==='undefined')return;charts.forEach(c=>c.destroy());charts=[];let rows=state.sets.filter(s=>s.exercise===name).map(s=>({...s,date:state.workouts.find(w=>w.id===s.workout_id)?.date})).sort((a,b)=>a.date.localeCompare(b.date)),by={};rows.forEach(s=>by[s.date]=Math.max(by[s.date]||0,s.kg));charts.push(new Chart(el,{type:'line',data:{labels:Object.keys(by).map(fmt),datasets:[{label:'Högsta vikt (kg)',data:Object.values(by),borderColor:'#c2f277',backgroundColor:'#c2f277'}]},options:{plugins:{legend:{labels:{color:'#cbd5e1'}}},scales:{x:{ticks:{color:'#94a3b8'}},y:{ticks:{color:'#94a3b8'}}}}}))}
function render(){charts.forEach(c=>c.destroy());charts=[];$('#content').innerHTML=({overview,calendar,training,weight,history,settings})[tab]();if(tab==='overview'||tab==='weight')drawWeight();if(tab==='history')drawExercise()}
refresh();
</script></body></html>'''
if __name__=='__main__':
 if not PIN:raise SystemExit('Ange APP_PIN som miljövariabel innan start.')
 app.run(host='127.0.0.1',port=int(os.environ.get('PORT','5000')))

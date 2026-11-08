import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

// Usage: node tests/verify_tv_finder.mjs [page.html] [--fixture]
const base=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const args=process.argv.slice(2),fixtureMode=args.includes('--fixture');
const file=args.find(a=>!a.startsWith('--'))||`${base}/TV_Shows_Android.html`;
const html=fs.readFileSync(file,'utf8');
const payload=html.match(/<script id="catalogue"[^>]*>([\s\S]*?)<\/script>/)[1];
const metaPayload=html.match(/<script id="metadata"[^>]*>([\s\S]*?)<\/script>/)[1];
const script=html.match(/<script>\s*('use strict';[\s\S]*?)<\/script>/)[1];
const data=JSON.parse(payload),meta=JSON.parse(metaPayload);
assert.ok(!/@@[A-Z]+@@/.test(html),'Template placeholders left in page');
assert.equal(new Set(data.map(m=>m.id)).size,data.length);
assert.ok(data.length>0);assert.equal(data.length,meta.total);
// Zac's inclusion rules, checked on every record.
for(const m of data){
 assert.ok(['tvSeries','tvMiniSeries'].includes(m.type),m.id);
 assert.ok(m.votes>=1000,m.id);
 const recent=m.score>=5&&m.lastYear>=2020,acclaimed=m.startYear>=2000&&m.score>8;
 assert.equal(m.recent,recent,m.id);assert.equal(m.acclaimed,acclaimed,m.id);assert.ok(recent||acclaimed,m.id);
 assert.ok(m.lastYear>=m.startYear,m.id);
 assert.match(m.imdb,/^https:\/\/www\.imdb\.com\/title\/tt\d+\/$/);
}
assert.ok(html.includes('Australian streaming, Rotten Tomatoes, classifications and languages are not yet collected for TV'));
assert.ok(html.includes('<a href="index.html">Movies</a><a href="tv.html" aria-current="page">TV shows</a><a href="foryou.html">For you</a><a href="new.html">New</a><a href="coming.html">Coming soon</a><a href="top20.html">Top 20</a>'));

class Element{
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.attrs={};this.dataset={};this.events={};this._text='';this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.open=false;this.className='';this.options=[];this.type='';this.min='';this.max='';this.classList={toggle:(name,flag)=>{const s=new Set(this.className.split(' ').filter(Boolean));flag?s.add(name):s.delete(name);this.className=[...s].join(' ');}};}
  set textContent(v){this._text=String(v);this.children=[];}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  append(...nodes){for(const node of nodes){if(node.tagName==='FRAGMENT')this.children.push(...node.children);else this.children.push(node);}}
  replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}
  setAttribute(k,v){this.attrs[k]=String(v);}
  addEventListener(type,fn){this.events[type]=fn;}
  querySelectorAll(selector){const all=this.children.flatMap(c=>[c,...c.querySelectorAll('*')]);return selector==='*'?all:all.filter(n=>n.tagName===selector.toUpperCase());}
  scrollIntoView(){}
  click(){this.events.click?.();}
}
function makeContext(storage=new Map()){
 const ids={};
 for(const match of html.matchAll(/<(\w+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)){
  const node=new Element(match[1]);node.id=match[3];for(const a of match[2].matchAll(/([\w-]+)="([^"]*)"/g)){node.attrs[a[1]]=a[2];if(['type','value','min','max','step'].includes(a[1]))node[a[1]]=a[2];}
  node.checked=/\bchecked(?:\s|$)/.test(match[2]);ids[node.id]=node;
 }
 for(const m of html.matchAll(/<select\b[^>]*id="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)){
  ids[m[1]].options=[...m[2].matchAll(/<option\b[^>]*value="([^"]*)"[^>]*>/g)].map(m=>({value:m[1]}));ids[m[1]].value=ids[m[1]].options[0]?.value||'';
 }
 ids.catalogue.textContent=payload;ids.metadata.textContent=metaPayload;
 const docRoot=new Element('html');
 const document={getElementById:id=>ids[id],createElement:tag=>new Element(tag),createDocumentFragment:()=>new Element('fragment'),documentElement:docRoot};
 const ctx=vm.createContext({document,localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},Intl,setTimeout,clearTimeout,scrollY:0,addEventListener:()=>{},getComputedStyle:()=>({colorScheme:'light'}),URL:{createObjectURL:()=> 'blob:fixture',revokeObjectURL:()=>{}},Blob,console});
 vm.runInContext(script,ctx);
 return{ctx,ids,storage,run:code=>vm.runInContext(code,ctx)};
}
const env=makeContext(),{ctx,ids,run}=env;
const count=()=>+ids.count.textContent.replace(/\D/g,'');
const walk=node=>[node,...node.children.flatMap(walk)];
const fire=(id,event='change',value)=>{if(value!==undefined)ids[id].value=String(value);ids[id].events[event]();};
const setCheck=(id,value)=>{ids[id].checked=value;fire(id);};
const matches=()=>JSON.parse(run('JSON.stringify(matches)'));
const DATA=JSON.parse(run('JSON.stringify(DATA)'));
const suspect=m=>m.score>=8.5&&m.votes<10000;
const DEFAULT_EX=['Romance','Horror','Documentary'];
const defaultOk=m=>m._groups.length&&!DEFAULT_EX.some(g=>m._groups.includes(g))
assert.ok(data.every(m=>!suspect(m)),'Likely vote-stuffed shows are left out of the data');

assert.equal(count(),meta.defaultResults,'Default count matches the builder');
assert.equal(count(),DATA.filter(m=>defaultOk(m)&&m.score>=6).length,'IMDb slider starts at 6.0');
assert.equal(ids.shows.children.length,Math.min(50,count()));
assert.ok(ids.shows.children.every(n=>n.tagName==='LI'&&n.children.length===3&&n.children[1].children.length===3));
assert.equal(ids['hide-suspect'],undefined);assert.equal(ids['min-votes'].value,'1000');
assert.equal(ids.genres.children.length,18);

// Open everything up, then test each control against an independent filter.
fire('clear-genres','click');setCheck('unknown-genres',true);fire('rating','input',5);assert.equal(count(),data.length);
for(let i=0;i<=50;i++){const v=(50+i)/10;fire('rating','input',v);assert.equal(count(),data.filter(m=>m.score>=v).length,`IMDb ${v}`);}
fire('rating','input',5);
for(const o of ids['min-votes'].options){fire('min-votes','change',o.value);assert.equal(count(),data.filter(m=>m.votes>=+o.value).length);}
fire('min-votes','change',1000);
fire('route-recent','click');assert.equal(count(),data.filter(m=>m.recent).length);assert.equal(ids['route-recent'].attrs['aria-pressed'],'true');
fire('route-acclaimed','click');assert.equal(count(),data.filter(m=>m.acclaimed).length);
fire('route-all','click');assert.equal(count(),data.length);
const typeBox=t=>walk(ids.types).find(x=>x.dataset.type===t);
for(const t of ['tvSeries','tvMiniSeries']){const b=typeBox(t);b.checked=true;b.events.change();assert.equal(count(),data.filter(m=>m.type===t).length);b.checked=false;b.events.change();}
for(const s of ['open','ended']){fire('status','change',s);assert.equal(count(),data.filter(m=>s==='open'?m.endYear==null:m.endYear!=null).length);}
fire('status','change','all');
const y0=+ids['year-min'].min,y1=+ids['year-max'].max;
fire('year-min','input',2010);fire('year-max','input',2005);assert.equal(ids['year-min'].value,'2005');assert.equal(count(),data.filter(m=>m.startYear===2005).length);
fire('year-max','input',y1);fire('year-min','input',y0);assert.equal(count(),data.length);
fire('last-min','input',2023);assert.equal(count(),data.filter(m=>m.lastYear>=2023).length);fire('last-min','input',ids['last-min'].min);assert.equal(count(),data.length);
const genreBox=(mode,g)=>walk(ids.genres).find(n=>n.dataset.mode===mode&&n.dataset.genre===g);
const tick=(mode,g)=>{const b=genreBox(mode,g);b.checked=true;b.events.change();};
tick('included','Comedy');tick('excluded','Talk & news');
assert.equal(count(),DATA.filter(m=>m._groups.includes('Comedy')&&!m._groups.includes('Talk & news')).length);
tick('included','Talk & news');assert.equal(genreBox('excluded','Talk & news').checked,false);fire('clear-genres','click');
assert.deepEqual(JSON.parse(run(`JSON.stringify(majorGenres(['Reality-TV','Game-Show','Talk-Show','News']))`)).sort(),['Reality & game shows','Talk & news']);

// Sorting, nulls last, pagination.
for(const o of ids.sort.options){fire('sort','change',o.value);const got=matches();assert.deepEqual(ids.shows.children.map(n=>n.dataset.id),got.slice(0,50).map(m=>m.id));
 if(o.value!=='title'){const f=o.value.replace(/-asc$/,''),asc=o.value.endsWith('-asc');const vals=got.map(m=>m[f]).filter(v=>typeof v==='number');for(let i=1;i<vals.length;i++)assert.ok(asc?vals[i]>=vals[i-1]:vals[i]<=vals[i-1],o.value);}}
fire('sort','change','score');
// One-tap sort buttons: tap once for newest/highest, again for oldest/lowest.
for(const f of ['startYear','lastYear','seasons','score']){fire('sort-'+f,'click');assert.equal(ids.sort.value,f);assert.equal(ids['sort-'+f].attrs['aria-pressed'],'true');fire('sort-'+f,'click');assert.equal(ids.sort.value,f+'-asc');const v=matches().map(m=>m[f]);for(let i=1;i<v.length;i++)assert.ok(v[i]>=v[i-1],f);}
fire('sort','change','score');
if(count()>50){fire('more','click');assert.equal(ids.shows.children.length,Math.min(100,count()));}
assert.ok(walk(ids.shows).filter(n=>n.tagName==='A'&&n.href).every(n=>n.href.startsWith('https://')));

// Search.
const first=data[0];fire('search','input',first.title);await new Promise(r=>setTimeout(r,180));assert.ok(matches().some(m=>m.id===first.id));
fire('search','input','zzzz-no-show-should-match-xyz');await new Promise(r=>setTimeout(r,180));assert.equal(count(),0);assert.equal(ids.empty.hidden,false);
fire('search','input','');await new Promise(r=>setTimeout(r,180));

if(fixtureMode){
 fire('reset-main','click');
 fire('search','input','grief');await new Promise(r=>setTimeout(r,180));assert.equal(count(),0,'Vote-stuffed title left out');
 fire('search','input','popular nine');await new Promise(r=>setTimeout(r,180));assert.equal(count(),1,'9.1 with 50k votes is not suspect');
 fire('search','input','romantic');await new Promise(r=>setTimeout(r,180));assert.equal(count(),1,'Search ignores the Romance default exclusion');
 fire('search','input','below six');await new Promise(r=>setTimeout(r,180));assert.equal(count(),1,'Search finds a 5.9 show below the 6.0 slider');
 fire('search','input','');await new Promise(r=>setTimeout(r,180));
}

// Saved settings, reset, theme and export.
fire('rating','input',7.5);fire('route-recent','click');
const saved=makeContext(env.storage);assert.equal(saved.ids.rating.value,'7.5');assert.equal(saved.run('state.route'),'recent');assert.equal(saved.run('matches.length'),count());
fire('reset-main','click');assert.equal(count(),meta.defaultResults);assert.equal(ids['rating-value'].textContent,'6.0+');assert.equal(run('state.route'),'all');
fire('done','click');assert.equal(ids.filters.open,false);fire('theme','click');assert.equal(ctx.document.documentElement.dataset.theme,'dark');fire('export','click');

console.log(JSON.stringify({tvRecords:data.length,defaultResults:meta.defaultResults,recent:meta.recent,acclaimedOnly:meta.acclaimedOnly,suspectHidden:meta.suspectHidden,status:'passed'}));

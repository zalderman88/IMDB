import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const base=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const html=fs.readFileSync(`${base}/Australian_Movies_Android.html`,'utf8');
const payload=html.match(/<script id="catalogue"[^>]*>([\s\S]*?)<\/script>/)[1];
const metaPayload=html.match(/<script id="metadata"[^>]*>([\s\S]*?)<\/script>/)[1];
const script=html.match(/<script>\s*('use strict';[\s\S]*?)<\/script>/)[1];
const data=JSON.parse(payload),meta=JSON.parse(metaPayload);
assert.equal(new Set(data.map(m=>m.id)).size,data.length);
assert.ok(!html.includes('@@DATA@@'));
assert.ok(html.includes('Rotten Tomatoes coverage is partial'));
assert.ok(html.includes('not complete copies'));
const passes=m=>(m.score>=6&&m.votes>=1000)||(m.critics>=60&&m.criticCount>=50)||(m.audience>=60&&m.audienceCount>=1000);
assert.ok(data.every(passes));assert.ok(data.every(m=>m.votes>=1000));
assert.ok(data.every(m=>!m.rt||m.rt.startsWith('https://www.rottentomatoes.com/m/')));
assert.ok(data.every(m=>!m.imdb||/^https:\/\/www\.imdb\.com\/title\/tt\d+\/$/.test(m.imdb)));
assert.ok(data.every(m=>!m.audienceCount||m.rtCountsChecked));
assert.ok(data.every(m=>!m.criticCount||m.rtCountsChecked));
assert.ok(data.every(m=>Object.keys(m.offers).every(k=>['nfx','prv','pmp','stn','dnp','mxx','atp'].includes(k))));

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
assert.equal(count(),meta.defaultResults);
assert.equal(ids.movies.children.length,Math.min(50,count()));
assert.ok(ids.movies.children.every(n=>n.tagName==='LI'&&n.className==='movie-row'));
assert.ok(ids.movies.children.every(n=>n.children.length===3));
assert.ok(ids.movies.children.every(n=>n.children[1].children.length===3));
assert.equal(ids.country.value,'exclude');assert.equal(ids['min-votes'].value,'1000');assert.equal(ids['min-critics'].value,'50');assert.equal(ids['min-audience'].value,'1000');

// Verify independent score routes and small-sample rejection with boundary cases.
ctx.fixtureCriteria={imdb:true,critics:true,audience:true,score:6,votes:1000,criticsScore:60,criticCount:50,audienceScore:60,audienceCount:1000};
const fixtures=[
 [{score:9,votes:999,critics:99,criticCount:500,audience:99,audienceCount:50000},false],
 [{score:8,votes:999,critics:99,criticCount:49,audience:99,audienceCount:999},false],
 [{score:6,votes:1000,critics:1,criticCount:200,audience:1,audienceCount:5000},true],
 [{score:4,votes:1500,critics:60,criticCount:50,audience:1,audienceCount:10},true],
 [{score:4,votes:1500,critics:1,criticCount:10,audience:60,audienceCount:1000},true],
 [{score:null,votes:null,critics:99,criticCount:null,audience:99,audienceCount:null},false],
 [{score:5.9,votes:1000000,critics:59,criticCount:500,audience:59,audienceCount:250000},false]
];
for(const [m,expected] of fixtures){ctx.fixture=m;assert.equal(run('Object.values(routes(fixture,fixtureCriteria)).some(Boolean)'),expected);}

fire('country','change','all');fire('clear-genres','click');setCheck('unknown-genres',true);assert.equal(count(),data.length);
for(const type of ['imdb','critics','audience']){
 for(const key of ['imdb','critics','audience'])setCheck('use-'+key,key===type);
 const slider=type==='imdb'?'rating':type;
 for(let i=0;i<=40;i++){
  const value=type==='imdb'?(60+i)/10:60+i;fire(slider,'input',value);
  const expected=data.filter(m=>type==='imdb'?m.score>=value&&m.votes>=1000:type==='critics'?m.critics>=value&&m.criticCount>=50:m.audience>=value&&m.audienceCount>=1000).length;
  assert.equal(count(),expected,`${type} ${value}`);
 }
 fire(slider,'input',type==='imdb'?6:60);
}
for(const key of ['imdb','critics','audience'])setCheck('use-'+key,true);
for(const [id,field,scoreField,threshold] of [['min-votes','votes','score',6],['min-critics','criticCount','critics',60],['min-audience','audienceCount','audience',60]]){
 const source=id==='min-votes'?'imdb':id==='min-critics'?'critics':'audience';
 for(const key of ['imdb','critics','audience'])setCheck('use-'+key,key===source);
 for(const option of ids[id].options){fire(id,'change',option.value);assert.equal(count(),data.filter(m=>m[field]>=+option.value&&m[scoreField]>=threshold).length);}
 fire(id,'change',id==='min-critics'?50:1000);
}
for(const key of ['imdb','critics','audience'])setCheck('use-'+key,true);
for(const service of ['nfx','prv','pmp','stn','dnp','mxx','atp']){
 const box=walk(ids.services).find(x=>x.dataset.service===service);box.checked=true;box.events.change();assert.equal(count(),data.filter(m=>m.offers[service]).length);box.checked=false;box.events.change();
}
assert.equal(ids.genres.children.length,16,'Only 16 high-level genre controls');
const grouped=JSON.parse(run(`JSON.stringify(majorGenres(['Comedy drama','Comedy horror','Science-fiction thriller']))`));
for(const label of ['Comedy','Drama & biography','Horror','Science fiction','Crime & thriller'])assert.ok(grouped.includes(label));
for(const classification of ['G','PG','M','MA15+','R18+','X18+','Unclassified','Unknown']){
 const box=walk(ids.classifications).find(x=>x.dataset.classification===classification);box.checked=true;box.events.change();assert.equal(count(),data.filter(m=>(m.classifications?.length?m.classifications:['Unknown']).includes(classification)).length);box.checked=false;box.events.change();
}
const pgBox=walk(ids.classifications).find(x=>x.dataset.classification==='PG'),mBox=walk(ids.classifications).find(x=>x.dataset.classification==='M');pgBox.checked=true;pgBox.events.change();mBox.checked=true;mBox.events.change();assert.equal(count(),data.filter(m=>m.classifications?.some(c=>['PG','M'].includes(c))).length);pgBox.checked=false;pgBox.events.change();mBox.checked=false;mBox.events.change();
assert.equal(ids.language.value,'all');
for(const language of ['english','foreign','unknown','all']){fire('language','change',language);assert.equal(count(),data.filter(m=>language==='all'||m.languageGroup===language).length);}
assert.ok(data.some(m=>m.languageGroup==='english'),'Known English-language films loaded');
assert.ok(data.some(m=>m.languageGroup==='foreign'),'Known foreign-language films loaded');
assert.ok(data.every(m=>['english','foreign','unknown'].includes(m.languageGroup)));
fire('scope-streaming','click');assert.equal(count(),data.filter(m=>Object.keys(m.offers).length).length);assert.equal(ids['scope-streaming'].attrs['aria-pressed'],'true');fire('scope-all','click');assert.equal(count(),data.length);

fire('year-min','input',2000);fire('year-max','input',1990);assert.equal(ids['year-min'].value,'1990');assert.equal(ids['year-max'].value,'1990');setCheck('unknown-year',false);assert.equal(count(),data.filter(m=>m.year===1990).length);
fire('year-max','input',ids['year-max'].max);fire('year-min','input',ids['year-min'].min);setCheck('unknown-year',true);
const genreBox=(mode,genre)=>walk(ids.genres).find(n=>n.dataset.mode===mode&&n.dataset.genre===genre);
function tick(mode,g){const box=genreBox(mode,g);assert.ok(box);box.checked=true;box.events.change();}
tick('included','Action & adventure');tick('included','Science fiction');tick('excluded','Crime & thriller');tick('excluded','Comedy');
assert.equal(count(),JSON.parse(run('JSON.stringify(DATA)')).filter(m=>(m._groups.includes('Action & adventure')||m._groups.includes('Science fiction'))&&!m._groups.includes('Crime & thriller')&&!m._groups.includes('Comedy')).length);
tick('included','Crime & thriller');assert.equal(genreBox('excluded','Crime & thriller').checked,false);tick('excluded','Action & adventure');assert.equal(genreBox('included','Action & adventure').checked,false);
fire('clear-genres','click');
fire('search','input','Interstellar');await new Promise(r=>setTimeout(r,180));assert.ok(count()>0);assert.ok(ids.movies.children.every(n=>n.children[0].children[0].textContent.toLowerCase().includes('interstellar')));
fire('search','input','zzzz-no-movie-should-match-xyz');await new Promise(r=>setTimeout(r,180));assert.equal(count(),0);assert.equal(ids.empty.hidden,false);
fire('search','input','');await new Promise(r=>setTimeout(r,180));

for(const option of ids.sort.options){fire('sort','change',option.value);const first=ids.movies.children.map(n=>n.dataset.id);assert.equal(first.length,50);const current=JSON.parse(run('JSON.stringify(matches.slice(0,50).map(m=>m.id))'));assert.deepEqual(first,current);if(option.value!=='title'){const field=option.value.replace(/-asc$/,''),asc=option.value.endsWith('-asc');const values=JSON.parse(run(`JSON.stringify(matches.map(m=>m[${JSON.stringify(field)}]))`));let seenNull=false,last=null;for(const value of values){if(value===null||value===undefined){seenNull=true;continue;}assert.ok(!seenNull,'Missing scores remain last');if(last!==null)assert.ok(asc?value>=last:value<=last,option.value);last=value;}}}
fire('sort','change','score');const firstIds=ids.movies.children.map(n=>n.dataset.id);fire('more','click');assert.equal(ids.movies.children.length,100);assert.deepEqual(ids.movies.children.slice(0,50).map(n=>n.dataset.id),firstIds);
assert.ok(walk(ids.movies).filter(n=>n.tagName==='A'&&n.href).every(n=>n.href.startsWith('https://')));
const rtLinks=walk(ids.movies).filter(n=>n.tagName==='A'&&n.href?.startsWith('https://www.rottentomatoes.com/'));assert.ok(rtLinks.length>0);
assert.ok(walk(ids.movies).filter(n=>n.className.includes('badge')).length>0);

fire('country','change','strict');assert.ok(JSON.parse(run('JSON.stringify(matches)')).every(m=>m.countries.length&&!m.countries.includes('IN')));
fire('country','change','exclude');assert.ok(JSON.parse(run('JSON.stringify(matches)')).every(m=>!m.countries.includes('IN')));
const stored=makeContext(env.storage);assert.equal(stored.ids.country.value,'exclude');assert.equal(stored.run('matches.length'),count());
fire('reset-main','click');assert.equal(count(),meta.defaultResults);assert.ok(walk(ids.classifications).filter(x=>x.tagName==='INPUT').every(x=>!x.checked));assert.equal(ids['rating-value'].textContent,'6.0+');assert.equal(ids['critics-value'].textContent,'60%+');assert.equal(ids['audience-value'].textContent,'60%+');assert.equal(ids.country.value,'exclude');assert.equal(ids.language.value,'all');assert.equal(ids['genre-summary'].textContent,'3 excluded');
fire('done','click');assert.equal(ids.filters.open,false);fire('theme','click');assert.equal(ctx.document.documentElement.dataset.theme,'dark');fire('export','click');

console.log(JSON.stringify({records:data.length,defaultResults:meta.defaultResults,rtReviewCountsChecked:meta.rtReviewCountsChecked,rtOnlyQualifiers:meta.rtOnlyQualifiers,services:meta.sourceCounts,checks:['Independent OR scores','Minimum vote/review boundary cases','Unverified RT counts rejected','123 slider positions','All adjustable review-count options','Seven Australian services','Year range and crossing handles','Sixteen major genres; compound-genre grouping and exclusions','Australian classification multiselect; Unknown separate','Country default allows unknown; reset preserved','Original-language filters: English, foreign, unknown, all','Search and empty state','Thirteen sorting choices; nulls last','Pagination','IMDb and RT review links','Saved filters, reset, theme and CSV export'],status:'passed'}));

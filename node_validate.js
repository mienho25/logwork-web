const fs = require('fs');
const data = fs.readFileSync('data.json', 'utf8'); // live API JSON
let script = fs.readFileSync('logwork.html', 'utf8').match(/<script>([\s\S]*)<\/script>/)[1];
// bake the data into EMBEDDED so boot() renders directly
script = script.replace('const EMBEDDED = /*__DATA__*/null;', 'const EMBEDDED = ' + data + ';');

const els = {};
function mkEl(){ return {innerHTML:'', textContent:'', value:'', addEventListener(){}, style:{}}; }
function get(sel){
  if(!els[sel]) els[sel]=mkEl();
  return els[sel];
}
global.document = { querySelector: get, getElementById: id => get('#'+id) };
global.window = {};
global.fetch = async () => ({ json: async () => JSON.parse(data) });
global.FileReader = function(){};

eval(script);

const grid = els['#grid'].innerHTML;
const rows = (grid.match(/<tr/g)||[]).length;
const grpHdr = (grid.match(/&#9660; ([^<]+)/g)||[]).map(s=>s.replace('&#9660; ',''));
const wkh = [...grid.matchAll(/class="wkh">([^<]+)</g)].map(m=>m[1]);
const bars = (grid.match(/class="bar"/g)||[]).length;
const baselines = (grid.match(/class="base"/g)||[]).length;
const hatches = (grid.match(/class="cell hatch"/g)||[]).length;
const members = (grid.match(/&#9654; /g)||[]).length;
const totals = (grid.match(/&rarr; Total &rarr;/g)||[]).length;
console.log('EMBEDDED data groups:', data ? JSON.parse(data).groups.length : '?');
console.log('rows:', rows);
console.log('week headers:', JSON.stringify(wkh));
console.log('group headers:', JSON.stringify(grpHdr));
console.log('member rows:', members, '| total rows:', totals);
console.log('progress bars:', bars, '| empty baselines:', baselines, '| weekend hatches:', hatches);
// show a couple sample member rows raw
const chip = grid.split('</tr>').filter(x=>x.includes('&#9654;')).slice(0,2).map(x=>x.replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim());
console.log('sample members:', chip);

const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assets=path.join(__dirname,'../src/robot_zoo');
const {deadzone,readPad}=require(path.join(assets,'input_mapping.js'));
const makePad=()=>({index:0,id:'Stadia Controller',mapping:'standard',axes:[0,0,0,0],buttons:Array.from({length:17},()=>({pressed:false}))});

test('standard Stadia axes, diagonal normalization, deadzone and button edges',()=>{
  const pad=makePad();
  pad.axes=[-1,-1,1,0];
  let frame=readPad(pad);
  assert.ok(frame.vx>0 && frame.vy>0 && frame.wz===-1);
  assert.ok(Math.abs(Math.hypot(frame.vx,frame.vy)-1)<1e-10);
  assert.equal(deadzone(.1),0);assert.equal(deadzone(NaN),0);
  pad.buttons[2].pressed=true;frame=readPad(pad);assert.equal(frame.action,'Low profile');
  assert.equal(readPad(pad,frame.buttons).action,null);
  pad.buttons[1].pressed=true;assert.equal(readPad(pad).action,'Stop');
});

test('D-pad means slow body translation, not turning',()=>{
  for(const [button,axis,sign] of [[12,'vx',1],[13,'vx',-1],[14,'vy',1],[15,'vy',-1]]) {
    const pad=makePad();pad.buttons[button].pressed=true;
    const frame=readPad(pad);assert.equal(frame[axis],sign*.35);assert.ok(frame.wz===0);
  }
});

function harness(robot='Unitree Go2') {
  class Element {
    constructor(){this.events={};this.style={};this.dataset={};this.parentElement={style:{}};this.isConnected=true;}
    addEventListener(type,fn){(this.events[type]??=[]).push(fn);}
    emit(type,event={}){for(const fn of this.events[type]||[])fn({preventDefault(){},target:{tagName:'DIV'},...event});}
    setAttribute(){} querySelector(){return new Element();} focus(){} setPointerCapture(){} getBoundingClientRect(){return {left:0,top:0,width:132,height:132};}
  }
  const nodes=new Map();const get=s=>{if(!nodes.has(s))nodes.set(s,new Element());return nodes.get(s);};
  const element=new Element();element.querySelector=get;
  const sticks=['move','turn'].map(which=>{const e=get(`[data-stick="${which}"]`);e.dataset.stick=which;return e;});
  const buttons=['Stand','Low profile','High profile','Stop'].map(action=>{const e=new Element();e.dataset.action=action;return e;});
  element.querySelectorAll=s=>s==='[data-stick]'?sticks:buttons;
  const window=new Element(),document=new Element();let focused=true,now=0,tick;
  document.hasFocus=()=>focused;document.hidden=false;
  const pad=makePad(),calls=[];
  const context={element,window,document,props:{value:robot},watch(){},AbortController,
    navigator:{getGamepads:()=>[pad]},performance:{now:()=>now},clearInterval(){},
    setInterval:fn=>{tick=fn;return 1;},server:{teleop:async(...frame)=>{calls.push(frame);return {ok:true,message:'Ready'};}}};
  vm.runInNewContext(fs.readFileSync(path.join(assets,'input_mapping.js'),'utf8')+'\n'+fs.readFileSync(path.join(assets,'joystick.js'),'utf8'),context);
  return {pad,window,document,sticks,buttons,calls,get,focus:value=>focused=value,
    async tick(){now+=60;tick();await new Promise(resolve=>setImmediate(resolve));}};
}

test('gamepad requires neutral, stop latches until release, focus loss sends one stop',async()=>{
  const h=harness();h.pad.axes[1]=-1;h.get('.pad-toggle').emit('click');await h.tick();
  assert.equal(h.calls.at(-1)[1],0);
  h.pad.axes[1]=0;await h.tick();h.pad.axes[1]=-1;await h.tick();assert.equal(h.calls.at(-1)[1],1);
  h.pad.buttons[1].pressed=true;await h.tick();assert.equal(h.calls.at(-1)[4],'Stop');
  h.pad.buttons[1].pressed=false;await h.tick();assert.equal(h.calls.at(-1)[1],0);
  h.pad.axes[1]=0;await h.tick();h.pad.axes[1]=-1;await h.tick();assert.equal(h.calls.at(-1)[1],1);
  h.focus(false);h.window.emit('blur');await h.tick();assert.equal(h.calls.at(-1)[4],'Stop');
  const length=h.calls.length;await h.tick();assert.equal(h.calls.length,length);
});

test('touch release, pointer cancellation, and Stop clear held movement',async()=>{
  const h=harness(),stick=h.sticks[0];
  const point={pointerId:1,button:0,clientX:66,clientY:26};
  stick.emit('pointerdown',point);await h.tick();assert.equal(h.calls.at(-1)[1],1);
  stick.emit('pointercancel',point);await h.tick();assert.equal(h.calls.at(-1)[1],0);
  stick.emit('pointerdown',point);await h.tick();h.buttons[3].emit('click');await h.tick();
  stick.emit('pointermove',point);await h.tick();assert.equal(h.calls.at(-1)[1],0);
});

test('Space suppresses a held keyboard key until it is released',async()=>{
  const h=harness();h.window.emit('keydown',{key:'w'});await h.tick();assert.equal(h.calls.at(-1)[1],1);
  h.window.emit('keydown',{key:' '});await h.tick();assert.equal(h.calls.at(-1)[4],'Stop');
  h.window.emit('keydown',{key:'w',repeat:true});await h.tick();assert.equal(h.calls.at(-1)[1],0);
  h.window.emit('keyup',{key:'w'});h.window.emit('keydown',{key:'w'});await h.tick();assert.equal(h.calls.at(-1)[1],1);
});


test('a centered screen stick takes control from a held gamepad and release stays stopped',async()=>{
  const h=harness();h.get('.pad-toggle').emit('click');await h.tick();
  h.pad.axes[1]=-1;await h.tick();assert.equal(h.calls.at(-1)[1],1);
  const point={pointerId:1,button:0,clientX:66,clientY:66};
  h.sticks[0].emit('pointerdown',point);await h.tick();assert.equal(h.calls.at(-1)[1],0);
  h.sticks[0].emit('pointermove',{...point,clientY:106});await h.tick();assert.equal(h.calls.at(-1)[1],-1);
  h.sticks[0].emit('pointerup',point);await h.tick();assert.equal(h.calls.at(-1)[1],0);
  h.pad.axes[1]=0;await h.tick();h.pad.axes[1]=-1;await h.tick();assert.equal(h.calls.at(-1)[1],1);
});

test('keyboard release does not resume a gamepad that is still deflected',async()=>{
  const h=harness();h.get('.pad-toggle').emit('click');await h.tick();
  h.pad.axes[1]=-1;await h.tick();
  h.window.emit('keydown',{key:'s'});await h.tick();assert.equal(h.calls.at(-1)[1],-1);
  h.window.emit('keyup',{key:'s'});await h.tick();assert.equal(h.calls.at(-1)[1],0);
});


test('joystick deflection scales with its resized dimensions',async()=>{
  const h=harness(),stick=h.sticks[0];
  stick.getBoundingClientRect=()=>({left:0,top:0,width:202,height:202});
  stick.emit('pointerdown',{pointerId:1,button:0,clientX:101,clientY:70.7});
  await h.tick();assert.ok(Math.abs(h.calls.at(-1)[1]-.5)<1e-8);
  stick.emit('pointermove',{pointerId:1,clientX:101,clientY:40.4});
  await h.tick();assert.equal(h.calls.at(-1)[1],1);
});


test('right joystick vertical input does nothing on screen and gamepad',async()=>{
  const h=harness();
  h.pad.axes[3]=-1;h.get('.pad-toggle').emit('click');await h.tick();
  h.pad.axes[2]=1;await h.tick();
  assert.equal(h.calls.at(-1)[3],-1);assert.equal(h.calls.at(-1)[4],null);
  h.pad.axes[2]=0;h.pad.axes[3]=1;await h.tick();
  assert.ok(h.calls.at(-1)[3] === 0);assert.equal(h.calls.at(-1)[4],null);
  const stick=h.sticks[1];
  stick.emit('pointerdown',{pointerId:1,button:0,clientX:66,clientY:0});
  await h.tick();assert.ok(h.calls.at(-1)[3] === 0);assert.equal(h.calls.at(-1)[4],null);
  stick.emit('pointermove',{pointerId:1,clientX:106,clientY:132});
  await h.tick();assert.equal(h.calls.at(-1)[3],-1);assert.equal(h.calls.at(-1)[4],null);
});


test('TurtleBot3 uses forward/back and separate turn with no strafe or poses',async()=>{
  const h=harness('TurtleBot3 Burger');h.get('.pad-toggle').emit('click');await h.tick();
  h.pad.axes=[1,-1,-1,1];await h.tick();
  let frame=h.calls.at(-1);assert.equal(frame[1],1);assert.equal(frame[2],0);assert.equal(frame[3],1);assert.equal(frame[4],null);
  h.pad.axes=[0,0,0,0];h.pad.buttons[2].pressed=true;await h.tick();assert.equal(h.calls.at(-1)[4],null);
  h.pad.buttons[2].pressed=false;h.pad.buttons[14].pressed=true;await h.tick();assert.equal(h.calls.at(-1)[3],.35);
  h.pad.buttons[14].pressed=false;h.window.emit('keydown',{key:'a'});await h.tick();
  assert.equal(h.calls.at(-1)[2],0);assert.equal(h.calls.at(-1)[3],1);
  h.window.emit('keyup',{key:'a'});await h.tick();
  const point={pointerId:1,button:0,clientX:106,clientY:66};
  h.sticks[0].emit('pointerdown',point);await h.tick();assert.equal(h.calls.at(-1)[2],0);assert.ok(h.calls.at(-1)[3]===0);
  h.sticks[0].emit('pointerup',point);
  h.sticks[1].emit('pointerdown',point);await h.tick();assert.equal(h.calls.at(-1)[3],-1);
});

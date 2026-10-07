const keys = new Set();
const blockedKeys = new Set();
const activePointers = new Set();
let inputEpoch = 0;
const points = {move: {x:0,y:0}, turn: {x:0,y:0}};
let enabled = false, engaged = false, neutralRequired = true;
let previousButtons = [], previousHeight = 0, pendingAction = null;
let busy = false, lastSent = 0, padId = null, alive = true, modeMessage = null;
const abort = new AbortController();
let bindings = new AbortController();
const listen = (target, event, fn) => target.addEventListener(event, fn, {signal: abort.signal});
const go2 = () => props.value === 'Unitree Go2';
const turtlebot = () => props.value === 'TurtleBot3 Burger';
const dualSticks = () => go2() || turtlebot();
const query = selector => element.querySelector(selector);
const status = text => { const node = query('.motion-status'); if(node) node.textContent=text; };
function draw(which, x, y) {
  const knob = query(`[data-stick="${which}"] .knob`);
  const stick = query(`[data-stick="${which}"]`);
  const travel = stick ? stick.getBoundingClientRect().width * .30 : 0;
  if(knob) knob.style.transform = `translate(${x*travel}px,${y*travel}px)`;
}
function clearInput() {
  for(const key of keys) blockedKeys.add(key);
  keys.clear();activePointers.clear();inputEpoch++;
  for (const which of ['move','turn']) { points[which] = {x:0,y:0}; draw(which,0,0); }
  neutralRequired = true; previousHeight = 0;
}
function stopInput(action = 'Stop') {
  clearInput(); engaged = true; pendingAction = action;
}
function disable() {
  enabled = false; clearInput();
  if(engaged) pendingAction = 'Stop';
  const toggle = query('.pad-toggle'); if(toggle) toggle.textContent = 'Enable gamepad';
}
function bind() {
  bindings.abort(); bindings = new AbortController();
  const bindListen = (target,event,fn) => target.addEventListener(event,fn,{signal:bindings.signal});
  query('.left-title').textContent = go2() ? 'Move / strafe' : turtlebot() ? 'Forward / back' : 'Move';
  query('.left-hint').textContent = turtlebot() ? 'W S' : 'W A S D';
  const moveStick = query('[data-stick="move"]');
  moveStick.setAttribute('aria-label', turtlebot() ? 'Drive joystick. W S forward and backward.' : 'Move joystick. W S forward backward, A D lateral movement.');
  for(const side of ['.west', '.east']) moveStick.querySelector(side).style.display = turtlebot() ? 'none' : '';
  query('[data-stick="turn"]').parentElement.style.display = dualSticks() ? '' : 'none';
  query('.pose-actions').style.display = go2() ? '' : 'none';
  query('.profile-note').style.display = go2() ? '' : 'none';
  query('.sticks').style.gridTemplateColumns = dualSticks() ? '' : 'minmax(0, 1fr) 100px';
  for(const stick of element.querySelectorAll('[data-stick]')) {
    const which = stick.dataset.stick;
    let pointerId = null, pointerEpoch = 0;
    function update(event) {
      const box=stick.getBoundingClientRect();
      let x=which === 'move' && turtlebot() ? 0 : (event.clientX-box.left-box.width/2)/(box.width * .30);
      let y=which === 'turn' ? 0 : (event.clientY-box.top-box.height/2)/(box.height * .30);
      const radius=Math.hypot(x,y); if(radius>1) { x/=radius;y/=radius; }
      points[which]={x,y}; draw(which,x,y);
    }
    bindListen(stick,'pointerdown',event => {
      if(pointerId!==null || event.button!==0) return;
      event.preventDefault();stick.focus();pointerId=event.pointerId;
      pointerEpoch=inputEpoch;activePointers.add(which);neutralRequired=true;
      stick.setPointerCapture(pointerId);engaged=true;update(event);
    });
    bindListen(stick,'pointermove',event => {if(event.pointerId===pointerId && pointerEpoch===inputEpoch) update(event);});
    const release = event => {
      if(event.pointerId!==pointerId) return;
      pointerId=null;activePointers.delete(which);neutralRequired=true;
      points[which]={x:0,y:0};draw(which,0,0);
    };
    bindListen(stick,'pointerup',release);bindListen(stick,'pointercancel',release);bindListen(stick,'lostpointercapture',release);
  }
  for(const button of element.querySelectorAll('[data-action]')) {
    bindListen(button,'click',()=>stopInput(button.dataset.action));
  }
  bindListen(query('.pad-toggle'),'click',()=>{
    enabled=!enabled;clearInput();engaged=true;
    query('.pad-toggle').textContent=enabled?'Disable gamepad':'Enable gamepad';
    if(!enabled) pendingAction='Stop';
  });
}
bind();
watch('value',()=>{disable();engaged=false;pendingAction=null;padId=null;modeMessage=null;bind();status('Ready · sticks centered');});
const accepted = new Set(['w','a','s','d','q','e','r','f','arrowup','arrowdown','arrowleft','arrowright',' ']);
listen(window,'keydown',event=>{
  if(!accepted.has(event.key.toLowerCase()) || /INPUT|TEXTAREA|SELECT/.test(event.target.tagName) || event.target.isContentEditable) return;
  event.preventDefault();
  if(event.repeat || blockedKeys.has(event.key.toLowerCase())) return;
  engaged=true;
  if(event.key===' ') stopInput();
  else keys.add(event.key.toLowerCase());
});
listen(window,'keyup',event=>{
  const key=event.key.toLowerCase();
  const released=keys.delete(key);blockedKeys.delete(key);
  if(released && !keys.size) neutralRequired=true;
});
listen(window,'blur',disable);
listen(document,'visibilitychange',()=>{if(document.hidden) disable();});
listen(window,'gamepaddisconnected',disable);
listen(window,'robot-zoo-reset-input',()=>{disable();engaged=false;pendingAction=null;});
function keyboard(positive,negative) {return Number(positive.some(k=>keys.has(k)))-Number(negative.some(k=>keys.has(k)));}
function frame() {
  if(!element.isConnected) {alive=false;abort.abort();bindings.abort();clearInterval(timer);return;}
  let pads=[], gamepadBlocked=false;
  try {pads=navigator.getGamepads?Array.from(navigator.getGamepads()).filter(Boolean):[];} catch (_) {gamepadBlocked=true;}
  const supported=pads.filter(p=>p.mapping==='standard');
  const pad=supported.find(p=>/stadia/i.test(p.id)) || supported[0];
  const padStatus=query('.pad-status');
  if(padStatus) padStatus.textContent=pad ? `Gamepad · ${enabled ?
    (neutralRequired?'Center sticks and release buttons':'Ready'):'Detected'}` :
    !navigator.getGamepads || gamepadBlocked ? 'This window cannot read gamepads · open the controller URL in Chrome' :
    pads.length ? 'Unmapped controller · try Chrome via the local URL' : 'Connect gamepad · press a button';
  const buttonIndex = {'Stand':0,'Stop':1,'Low profile':2,'High profile':3};
  for(const button of element.querySelectorAll('[data-action]')) {
    button.dataset.active = String(!!(enabled && pad?.buttons[buttonIndex[button.dataset.action]]?.pressed));
  }
  let input={vx:0,vy:0,wz:0,height:0,action:null};
  if(enabled && pad && document.hasFocus() && !document.hidden) {
    if(padId!==pad.index) {padId=pad.index;neutralRequired=true;previousButtons=[];}
    input=readPad(pad,previousButtons,!turtlebot()); previousButtons=input.buttons;
    if(turtlebot()) {
      input.vy=0;
      input.wz += .35 * (Number(input.buttons[14]) - Number(input.buttons[15]));
    }
    const neutral= !input.vx && !input.vy && !input.wz && !input.height && !input.buttons.some(Boolean);
    if(neutralRequired) {
      if(neutral) neutralRequired=false;
      input={vx:0,vy:0,wz:0,height:0,action:input.action==='Stop'?'Stop':null};
    }
  } else if(enabled && padId!==null) {disable();padId=null;}
  if(input.action==='Stop') stopInput();
  else if(input.action && go2()) stopInput(input.action);
  // Manual controls own all axes, including centered sticks. Releasing them
  // requires the physical pad to return to neutral before it can take over.
  if(activePointers.size || keys.size) input={vx:0,vy:0,wz:0,height:0,action:null};
  if(activePointers.has('move') || keys.size) {
    input.vx= -points.move.y + keyboard(['w','arrowup'],['s','arrowdown']);
    input.vy= -points.move.x + keyboard(['a','arrowleft'],['d','arrowright']);
  }
  if(activePointers.has('turn') || keys.size) {
    input.wz= -points.turn.x + keyboard(['q'],['e']);
    input.height= keyboard(['r'],['f']);
  }
  const height= input.height>.65?1:input.height<-.65?-1:0;
  if(height && height!==previousHeight && go2()) stopInput(height>0?'High profile':'Low profile');
  previousHeight=height;
  const radius=Math.max(1,Math.hypot(input.vx,input.vy));input.vx/=radius;input.vy/=radius;
  if(turtlebot()) {input.wz += keyboard(['a','arrowleft'],['d','arrowright']);input.vy=0;}
  else if(!go2()) {input.wz=input.vy;input.vy=0;}
  input.wz=Math.max(-1,Math.min(1,input.wz));
  if(pendingAction) {input.vx=0;input.vy=0;input.wz=0;}
  if(enabled && pad && !activePointers.size && !keys.size) {
    draw('move',-input.vy,-input.vx);draw('turn',-input.wz,0);
  }
  if(!engaged || busy || performance.now()-lastSent<50) return;
  const action=pendingAction;pendingAction=null;busy=true;lastSent=performance.now();
  if(!document.hasFocus() || document.hidden) engaged=false;
  server.teleop(props.value,input.vx,input.vy,input.wz,action).then(response=>{
    if(!response?.ok) throw new Error(response?.message || 'Connection lost');
    if(action) modeMessage = response.message;
    if(input.vx || input.vy || input.wz) modeMessage = null;
    if(alive) status(modeMessage || response.message);
  }).catch(()=>{disable();engaged=false;pendingAction=null;status('Connection lost · movement times out automatically');})
    .finally(()=>{busy=false;});
}
const timer=setInterval(frame,25);

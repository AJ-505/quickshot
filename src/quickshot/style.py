"""Application CSS.

Deliberately restrained: the screenshot is the subject, the chrome recedes.
"""

CSS = b"""
window.qs-window {
  background-color: #0d0d10;
}

.quickshot-canvas {
  background-color: #0d0d10;
}

.qs-toolbar {
  background-color: rgba(28, 28, 33, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 14px;
  padding: 5px;
  box-shadow: 0 6px 26px rgba(0, 0, 0, 0.55);
}

.qs-toolbar button {
  background: transparent;
  border: none;
  border-radius: 10px;
  padding: 6px;
  min-width: 0;
  min-height: 0;
  margin: 0;
  box-shadow: none;
  outline: none;
}

.qs-toolbar button:hover {
  background-color: rgba(255, 255, 255, 0.10);
}

.qs-toolbar button:active {
  background-color: rgba(255, 255, 255, 0.18);
}

.qs-toolbar button:checked,
.qs-toolbar togglebutton.qs-tool:checked {
  background-color: #3c6df0;
}

.qs-toolbar button.qs-primary {
  background-color: rgba(60, 109, 240, 0.20);
}
.qs-toolbar button.qs-primary:hover {
  background-color: rgba(60, 109, 240, 0.34);
}
.qs-toolbar button.qs-danger:hover {
  background-color: rgba(224, 49, 49, 0.32);
}

.qs-toolbar separator {
  background-color: rgba(255, 255, 255, 0.13);
  min-width: 1px;
  min-height: 20px;
  margin: 2px 5px;
}

.qs-popover {
  background-color: rgba(28, 28, 33, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px;
}

.qs-popover button {
  background: transparent;
  border: none;
  border-radius: 8px;
  padding: 3px;
}
.qs-popover button:hover {
  background-color: rgba(255, 255, 255, 0.12);
}

/* --- text entry overlay --- */
window.qs-entry {
  background-color: transparent;
}
window.qs-entry decoration {
  background: none;
  box-shadow: none;
}
.qs-entry-frame {
  background-color: rgba(20, 20, 25, 0.97);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 10px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.6);
}
.qs-entry entry {
  background: transparent;
  color: #ffffff;
  font-size: 15px;
  font-weight: bold;
  padding: 9px 12px;
  caret-color: #ffffff;
}
.qs-entry-hint {
  color: rgba(255, 255, 255, 0.55);
  font-size: 11px;
  padding: 0 12px 8px 12px;
}

/* --- help overlay --- */
.qs-help {
  background-color: rgba(18, 18, 22, 0.97);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 16px;
  padding: 22px 26px;
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.7);
}
.qs-help h1 {
  font-size: 15px;
  font-weight: bold;
  color: #ffffff;
  margin: 0 0 14px 0;
}
.qs-help .row {
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.82);
}
.qs-help .k {
  min-width: 96px;
  color: #8fb4ff;
  font-weight: bold;
}
.qs-help .col {
  margin-right: 34px;
}
.qs-help .foot {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.45);
  margin-top: 16px;
}
"""

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
  border-radius: 9px;
  padding: 4px 5px;
  min-width: 0;
  min-height: 0;
  margin: 0;
  box-shadow: none;
  outline: none;
  color: rgba(255, 255, 255, 0.88);
}

.qs-toolbar button:hover {
  background-color: rgba(255, 255, 255, 0.09);
}

.qs-toolbar button:active {
  background-color: rgba(255, 255, 255, 0.16);
}

.qs-toolbar button:checked,
.qs-toolbar togglebutton.qs-tool:checked {
  background-color: #3c6df0;
  color: #ffffff;
}

.qs-toolbar button.qs-primary {
  background-color: rgba(60, 109, 240, 0.22);
}
.qs-toolbar button.qs-primary:hover {
  background-color: rgba(60, 109, 240, 0.38);
}
.qs-toolbar button.qs-danger:hover {
  background-color: rgba(224, 49, 49, 0.32);
}

.qs-key {
  font-size: 9px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.46);
}
button:checked .qs-key {
  color: rgba(255, 255, 255, 0.85);
}
.qs-stroke {
  padding: 4px 5px;
}

.qs-toolbar separator {
  background-color: rgba(255, 255, 255, 0.12);
  min-width: 1px;
  min-height: 24px;
  margin: 4px 4px;
}

.qs-popover contents {
  background-color: rgba(28, 28, 33, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px;
}

.qs-popover button {
  background: transparent;
  border: none;
  border-radius: 8px;
  padding: 3px;
  min-width: 0;
  min-height: 0;
  box-shadow: none;
}
.qs-popover button:hover {
  background-color: rgba(255, 255, 255, 0.12);
}

window.qs-entry {
  background-color: transparent;
}
.qs-entry {
  opacity: 0;
  min-width: 1px;
  min-height: 1px;
  padding: 0;
  margin: 0;
  border: none;
  background: none;
  box-shadow: none;
}

.qs-help {
  background-color: rgba(18, 18, 22, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 16px;
  padding: 22px 24px 18px 24px;
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.7);
}
.qs-help-title {
  font-size: 17px;
  font-weight: 700;
  color: #ffffff;
  margin-bottom: 12px;
}
.qs-help-head {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: rgba(255, 255, 255, 0.42);
  margin-bottom: 4px;
}
.qs-help-desc {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.86);
}
.qs-help-or {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.35);
}
.qs-keycap {
  font-size: 11.5px;
  font-weight: 600;
  color: #dbe6ff;
  background-color: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-bottom-width: 2px;
  border-radius: 6px;
  padding: 1px 7px;
  min-width: 14px;
}
.qs-help-foot {
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.55);
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.09);
}
"""

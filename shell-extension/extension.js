import GLib from 'gi://GLib';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const APP_ID = 'dev.quickshot.Quickshot';
const RETRY_MS = [0, 120, 400];

function isQuickshot(win) {
    try {
        return win?.get_gtk_application_id?.() === APP_ID;
    } catch {
        return false;
    }
}

function raise(win) {
    if (!isQuickshot(win) || win.has_focus())
        return;
    Main.activateWindow(win);
}

export default class QuickshotFocusExtension extends Extension {
    enable() {
        this._timers = new Set();
        this._created = global.display.connect('window-created', (_d, win) => {
            for (const ms of RETRY_MS) {
                const id = GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => {
                    this._timers.delete(id);
                    raise(win);
                    return GLib.SOURCE_REMOVE;
                });
                this._timers.add(id);
            }
        });
        this._attention = global.display.connect('window-demands-attention', (_d, win) => raise(win));
    }

    disable() {
        global.display.disconnect(this._created);
        global.display.disconnect(this._attention);
        for (const id of this._timers)
            GLib.source_remove(id);
        this._timers = null;
    }
}

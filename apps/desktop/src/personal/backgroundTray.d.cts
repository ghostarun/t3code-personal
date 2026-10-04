import type { BrowserWindow } from "electron";
export function initialize(options: {
  platform: string;
  baseDir: string;
  switcherHelper: string;
  iconPath: string | undefined;
}): Promise<void>;
export function attachMainWindow(window: BrowserWindow): void;
export function conceal(): void;
export function allowQuit(): void;
export function forceQuit(): void;

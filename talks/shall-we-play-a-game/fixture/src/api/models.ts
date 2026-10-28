/**
 * Mission Log API
 * Generated from api/openapi.json. DO NOT EDIT.
 */
export type MissionStatus = 'open' | 'done';

export interface Mission {
  id: string;
  title: string;
  status: MissionStatus;
  priority: 1 | 2 | 3;
}

export interface MissionStatusUpdate {
  status: MissionStatus;
}

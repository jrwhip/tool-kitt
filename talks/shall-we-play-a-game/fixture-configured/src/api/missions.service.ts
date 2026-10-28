/**
 * Mission Log API
 * Generated from api/openapi.json. DO NOT EDIT.
 */
import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { Mission, MissionStatusUpdate } from './models';

@Injectable({ providedIn: 'root' })
export class MissionsService {
  private readonly http = inject(HttpClient);
  private readonly basePath = '/api';

  /** GET /api/missions — operationId listMissions */
  listMissions(): Observable<Mission[]> {
    return this.http.get<Mission[]>(`${this.basePath}/missions`);
  }

  /** PATCH /api/missions/{id} — operationId updateMissionStatus */
  updateMissionStatus(id: string, body: MissionStatusUpdate): Observable<Mission> {
    return this.http.patch<Mission>(`${this.basePath}/missions/${encodeURIComponent(id)}`, body);
  }
}

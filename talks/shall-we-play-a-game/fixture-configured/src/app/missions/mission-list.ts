import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MissionsService } from '../../api';

@Component({
  selector: 'app-mission-list',
  templateUrl: './mission-list.html',
  styleUrl: './mission-list.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MissionList {
  private readonly missionsApi = inject(MissionsService);

  /** `undefined` until the first response lands; the template shows a loading row until then. */
  protected readonly missions = toSignal(this.missionsApi.listMissions());
}

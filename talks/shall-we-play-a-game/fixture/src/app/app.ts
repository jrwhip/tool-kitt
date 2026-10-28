import { ChangeDetectionStrategy, Component } from '@angular/core';
import { MissionList } from './missions/mission-list';

@Component({
  selector: 'app-root',
  imports: [MissionList],
  templateUrl: './app.html',
  styleUrl: './app.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {}

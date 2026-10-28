import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Mission } from '../../api';
import { MissionList } from './mission-list';

const MISSIONS: Mission[] = [
  { id: 'm-1', title: 'Calibrate the dish', status: 'open', priority: 1 },
  { id: 'm-2', title: 'Rotate the launch codes', status: 'done', priority: 2 },
  { id: 'm-3', title: 'Play tic-tac-toe', status: 'open', priority: 3 },
];

describe('MissionList', () => {
  let fixture: ComponentFixture<MissionList>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MissionList],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(MissionList);
  });

  afterEach(() => http.verify());

  function respond(missions: Mission[]): void {
    http.expectOne('/api/missions').flush(missions);
    fixture.detectChanges();
  }

  it('shows a loading row before the API answers', async () => {
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.loading')?.textContent).toContain('Loading');
    http.expectOne('/api/missions');
  });

  it('renders one row per mission', async () => {
    await fixture.whenStable();
    respond(MISSIONS);
    const rows = (fixture.nativeElement as HTMLElement).querySelectorAll('li.mission');
    expect(rows.length).toBe(3);
    expect(rows[1].textContent).toContain('Rotate the launch codes');
  });

  it('marks done missions', async () => {
    await fixture.whenStable();
    respond(MISSIONS);
    const rows = (fixture.nativeElement as HTMLElement).querySelectorAll('li.mission');
    expect(rows[1].classList.contains('done')).toBe(true);
    expect(rows[0].classList.contains('done')).toBe(false);
  });

  it('shows the empty state for an empty log', async () => {
    await fixture.whenStable();
    respond([]);
    expect((fixture.nativeElement as HTMLElement).querySelector('.empty')).not.toBeNull();
  });
});

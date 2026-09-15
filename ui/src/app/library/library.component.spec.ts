import { TestBed } from '@angular/core/testing';
import { HttpClient } from '@angular/common/http';
import { Subject, of } from 'rxjs';
import { ArchiveItem, ArchivedComment, LibraryComponent, matchesSearch, threadComments } from './library.component';
import { MeTubeSocket } from '../services/metube-socket.service';

const video: ArchiveItem = {
  id: 'video', title: 'one two three four five six seven eight hidden phrase',
  creator: 'Some Creator', description: 'Useful description', downloaded_at: null,
  source: 'https://example.com', available: true, thumbnail: true, download_type: 'video', warning: '',
};

describe('Archive', () => {
  it('searches undisplayed title words, creator and description', () => {
    expect(matchesSearch(video, 'hidden phrase')).toBe(true);
    expect(matchesSearch(video, 'CREATOR useful')).toBe(true);
    expect(matchesSearch(video, 'absent')).toBe(false);
  });

  it('orders replies and tolerates cycles and missing parents', () => {
    const comments = [
      { id: 'reply', parent: 'root' }, { id: 'root', parent: null },
      { id: 'a', parent: 'b' }, { id: 'b', parent: 'a' }, { id: 'orphan', parent: 'missing' },
    ] as ArchivedComment[];
    const ordered = threadComments(comments);
    expect(ordered.length).toBe(5);
    expect(ordered.find(comment => comment.id === 'reply')?.depth).toBe(1);
    expect(ordered.findIndex(comment => comment.id === 'root')).toBeLessThan(ordered.findIndex(comment => comment.id === 'reply'));
  });

  it('renders a local player, formatted text safely and the no-comments message', async () => {
    const comment = { id: 'one', parent: null, author: 'Person', text: '<script>alert(1)</script>', timestamp: null, time_text: '', likes: 0, author_is_uploader: false };
    let response: ArchiveItem = { ...video, comments: [comment] };
    await TestBed.configureTestingModule({
      imports: [LibraryComponent],
      providers: [
        { provide: HttpClient, useValue: { get: () => of(response) } },
        { provide: MeTubeSocket, useValue: { fromEvent: () => new Subject() } },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(LibraryComponent);
    fixture.componentRef.setInput('route', '#/archive/video');
    fixture.detectChanges();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector('video')?.getAttribute('src')).toBe('library/video/media');
    expect(element.querySelector('.comment')?.textContent).toContain('<script>alert(1)</script>');
    expect(element.querySelector('script')).toBeNull();
    response = { ...video, comments: [] };
    fixture.componentRef.setInput('route', '#/archive/another');
    fixture.detectChanges();
    expect(element.textContent).toContain('Comments were not archived for this video.');
  });
});

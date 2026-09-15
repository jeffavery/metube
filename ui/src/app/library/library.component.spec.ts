import { TestBed } from '@angular/core/testing';
import { HttpClient } from '@angular/common/http';
import { Subject, of } from 'rxjs';
import { ArchiveItem, ArchivedComment, LibraryComponent, matchesCategory, matchesSearch, threadComments } from './library.component';
import { MeTubeSocket } from '../services/metube-socket.service';

const video: ArchiveItem = {
  id: 'video', title: 'one two three four five six seven eight hidden phrase',
  creator: 'Some Creator', description: 'Useful description', downloaded_at: null,
  source: 'https://example.com', available: true, thumbnail: true, download_type: 'video', warning: '',
};

describe('Archive', () => {
  it('supports multiple memberships, uncategorized and search within a category', () => {
    const categorized = { ...video, categories: ['3D Printing', 'Electronics'] };
    expect(matchesCategory(categorized, '3D Printing')).toBe(true);
    expect(matchesCategory(categorized, 'Electronics')).toBe(true);
    expect(matchesCategory(categorized, 'Funny Stuff')).toBe(false);
    expect(matchesCategory(categorized, null)).toBe(false);
    expect(matchesCategory(video, null)).toBe(true);
    expect(matchesCategory(categorized, undefined)).toBe(true);
    expect(matchesCategory(categorized, 'Electronics') && matchesSearch(categorized, 'hidden phrase')).toBe(true);
  });

  it('saves multiple selected categories and creates a new category', async () => {
    const post = vi.fn().mockReturnValue(of({ status: 'ok' }));
    await TestBed.configureTestingModule({
      imports: [LibraryComponent],
      providers: [
        { provide: HttpClient, useValue: { post, get: () => of([]) } },
        { provide: MeTubeSocket, useValue: { fromEvent: () => new Subject() } },
      ],
    }).compileComponents();
    const component = TestBed.createComponent(LibraryComponent).componentInstance;
    component.editCategories(video);
    component.toggleCategory('3D Printing');
    component.toggleCategory('Electronics');
    component.saveCategories();
    expect(post).toHaveBeenCalledWith('library/video/categories', { categories: ['3D Printing', 'Electronics'] });
    expect(component.editingId).toBe('');
    component.newCategory = 'Projects';
    component.createCategory();
    expect(post).toHaveBeenCalledWith('library/categories', { name: 'Projects' });
    expect(component.newCategory).toBe('');
  });
  it('requires confirmation before deleting archived media', async () => {
    const post = vi.fn().mockReturnValue(of({ status: 'ok' }));
    await TestBed.configureTestingModule({
      imports: [LibraryComponent],
      providers: [
        { provide: HttpClient, useValue: { post, get: () => of([]) } },
        { provide: MeTubeSocket, useValue: { fromEvent: () => new Subject() } },
      ],
    }).compileComponents();
    const component = TestBed.createComponent(LibraryComponent).componentInstance;
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    component.deleteMedia(video);
    expect(post).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    component.deleteMedia(video);
    expect(post).toHaveBeenCalledWith('library/delete-media', { id: video.id });
    expect(component.deletingId).toBe('');
    confirm.mockRestore();
  });
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

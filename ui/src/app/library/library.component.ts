import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, Input, OnChanges, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subscription } from 'rxjs';
import { MeTubeSocket } from '../services/metube-socket.service';

export interface ArchivedComment {
  id: string;
  parent: string | null;
  author: string;
  text: string;
  timestamp: number | null;
  time_text: string;
  likes: number | null;
  author_is_uploader: boolean;
}

export interface ArchiveItem {
  id: string;
  title: string;
  creator: string;
  description: string;
  downloaded_at: number | null;
  source: string;
  available: boolean;
  thumbnail: boolean;
  download_type: string;
  warning: string;
  comments?: ArchivedComment[];
}

export function shortTitle(title: string): string {
  const words = title.trim().split(/\s+/);
  return words.length > 8 ? words.slice(0, 8).join(' ') + '…' : title;
}

export function matchesSearch(item: ArchiveItem, query: string): boolean {
  const haystack = [item.title, item.creator, item.description, item.source].join(' ').toLocaleLowerCase();
  return query.trim().toLocaleLowerCase().split(/\s+/).every(word => haystack.includes(word));
}

// Iterative traversal also handles missing parents, duplicate roots and cycles
// from platform metadata, without recursion or trusting HTML in comments.
export function threadComments(comments: ArchivedComment[]): (ArchivedComment & { depth: number })[] {
  const ids = new Set(comments.map(comment => comment.id));
  const children = new Map<string, ArchivedComment[]>();
  for (const comment of comments) {
    if (comment.parent && ids.has(comment.parent)) {
      const siblings = children.get(comment.parent) ?? [];
      siblings.push(comment);
      children.set(comment.parent, siblings);
    }
  }
  const roots = comments.filter(comment => !comment.parent || !ids.has(comment.parent));
  const seen = new Set<string>();
  const result: (ArchivedComment & { depth: number })[] = [];
  for (const root of [...roots, ...comments]) {
    const stack = [{ comment: root, depth: 0 }];
    while (stack.length) {
      const { comment, depth } = stack.pop()!;
      if (seen.has(comment.id)) continue;
      seen.add(comment.id);
      result.push({ ...comment, depth: Math.min(depth, 4) });
      for (const child of [...(children.get(comment.id) ?? [])].reverse()) {
        stack.push({ comment: child, depth: depth + 1 });
      }
    }
  }
  return result;
}

@Component({
  selector: 'app-library',
  imports: [FormsModule, DatePipe],
  templateUrl: './library.component.html',
  styleUrl: './library.component.sass',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LibraryComponent implements OnChanges, OnInit {
  @Input() route = '';
  private http = inject(HttpClient);
  private cdr = inject(ChangeDetectorRef);
  private socket = inject(MeTubeSocket);
  private destroyRef = inject(DestroyRef);
  private request?: Subscription;
  items: ArchiveItem[] = [];
  selected: ArchiveItem | null = null;
  comments: (ArchivedComment & { depth: number })[] = [];
  commentLimit = 100;
  query = '';
  loading = false;
  error = '';
  shortTitle = shortTitle;

  ngOnInit() {
    this.socket.fromEvent('library_changed').pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.reload());
    this.socket.fromEvent('connect').pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.reload());
  }

  ngOnChanges() { this.reload(); }

  get filteredItems() { return this.items.filter(item => matchesSearch(item, this.query)); }

  get playId(): string {
    return this.route.startsWith('#/archive/') ? this.route.substring('#/archive/'.length) : '';
  }

  playLink(item: ArchiveItem) { return '#/archive/' + item.id; }
  mediaLink(item: ArchiveItem) { return 'library/' + encodeURIComponent(item.id) + '/media'; }
  thumbnailLink(item: ArchiveItem) { return 'library/' + encodeURIComponent(item.id) + '/thumbnail'; }

  hideThumbnail(event: Event) { (event.target as HTMLImageElement).hidden = true; }

  reload() {
    this.request?.unsubscribe();
    this.loading = true;
    this.error = '';
    this.selected = null;
    this.comments = [];
    this.commentLimit = 100;
    const id = this.playId;
    const url = id ? 'library/' + encodeURIComponent(id) : 'library';
    this.request = this.http.get<ArchiveItem | ArchiveItem[]>(url)
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: data => {
          if (Array.isArray(data)) this.items = data;
          else {
            this.selected = data;
            this.comments = threadComments(data.comments ?? []);
          }
          this.loading = false;
          this.cdr.markForCheck();
        },
        error: () => {
          this.error = id ? 'This archived video could not be loaded.' : 'The archive could not be loaded.';
          this.loading = false;
          this.cdr.markForCheck();
        },
      });
  }
}

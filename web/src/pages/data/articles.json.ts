import articles from '../../data/articles.json';

export const prerender = true;

export async function GET() {
  return new Response(JSON.stringify(articles), {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'public, max-age=300',
    },
  });
}

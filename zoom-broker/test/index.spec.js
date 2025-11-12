import { env, createExecutionContext, waitOnExecutionContext, SELF } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';
import worker from '../src';

describe('OAuth broker worker', () => {
    it('start returns 200 on POST /zoom/auth/start', async () => {
        const request = new Request('http://example.com/zoom/auth/start', { method: 'POST' });
        const ctx = createExecutionContext();
        const response = await worker.fetch(request, env, ctx);
        await waitOnExecutionContext(ctx);
        expect(response.status).toBe(200);
        const body = await response.json();
        expect(body).toHaveProperty('auth_url');
        expect(body).toHaveProperty('session_id');
    });

    it('poll without id returns 400', async () => {
        const request = new Request('http://example.com/zoom/auth/poll', { method: 'GET' });
        const ctx = createExecutionContext();
        const response = await worker.fetch(request, env, ctx);
        await waitOnExecutionContext(ctx);
        expect(response.status).toBe(400);
    });

    it('callback without code/state returns 400', async () => {
        const request = new Request('http://example.com/callback', { method: 'GET' });
        const ctx = createExecutionContext();
        const response = await worker.fetch(request, env, ctx);
        await waitOnExecutionContext(ctx);
        expect(response.status).toBe(400);
    });

    it('refresh without token returns 400', async () => {
        const request = new Request('http://example.com/zoom/token/refresh', { method: 'POST', body: '{}' , headers: { 'content-type': 'application/json' }});
        const ctx = createExecutionContext();
        const response = await worker.fetch(request, env, ctx);
        await waitOnExecutionContext(ctx);
        expect(response.status).toBe(400);
    });
    it('responds 404 on unknown path (unit style)', async () => {
        const request = new Request('http://example.com/unknown');
        const ctx = createExecutionContext();
        const response = await worker.fetch(request, env, ctx);
        await waitOnExecutionContext(ctx);
        expect(response.status).toBe(404);
        expect(await response.text()).toBe('Not found');
    });

    it('responds 404 on unknown path (integration style)', async () => {
        const response = await SELF.fetch('http://example.com/unknown');
        expect(response.status).toBe(404);
        expect(await response.text()).toBe('Not found');
    });
});

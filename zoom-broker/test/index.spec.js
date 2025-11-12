import { env, createExecutionContext, waitOnExecutionContext, SELF } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';
import worker from '../src';

describe('OAuth broker worker', () => {
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

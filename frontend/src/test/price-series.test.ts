import {describe,it,expect} from "vitest";import {normalizePriceSeries} from "@/lib/price-series";
describe("verified price-series normalization",()=>{const now=1800000000000;
 it("rejects future/old/bad prices and orders by event time",()=>{const x=normalizePriceSeries({points:[{timestamp:now-10,price:3},{timestamp:now-100,price:2},{timestamp:now+3,price:5},{timestamp:now-10000000,price:7},{timestamp:now-30,price:-1}]}, "BTCUSDT",now);expect(x.points.map(p=>p.price)).toEqual([2,3]);expect(x.status).toBe("INSUFFICIENT_HISTORY")});
 it("accepts three genuine observations and suppresses zero-fill",()=>{const x=normalizePriceSeries({points:[{timestamp:now-30,price:3},{timestamp:now-20,price:4},{timestamp:now-10,price:5}]}, "BTCUSDT",now);expect(x.status).toBe("AVAILABLE");expect(x.points).toHaveLength(3)});
});

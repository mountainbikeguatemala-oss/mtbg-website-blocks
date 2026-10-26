/**
 * The count-up, shared by the Reviews blocks' five-star total and the Counter block (s_mtbg_counter): a number
 * counting up to its target once it comes into view, along a speed curve (the Reviews page's "Count-up speed").
 */
export const COUNT_MS = 5000; // the count-up's length: long, slowing right down as it reaches the total

/** How the count-up's speed changes on the way to the total (a preset's "Count-up speed"), t from 0 to 1. */
export const EASINGS = {
    linear: (t) => t, // steady
    smooth: (t) => 1 - Math.pow(1 - t, 3),
    slow: (t) => 1 - Math.pow(1 - t, 5), // fast at first, slower and slower to the end (the blocks' own)
    slower: (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)),
    log: (t) => Math.log1p(99 * t) / Math.log(100),
};

/** The count-up options of a block (data-count-ms, data-count-ease; blocks without them: 5 s, slowing down). */
export function countOptions(el) {
    const ms = parseInt(el.dataset.countMs);
    return { ms: Number.isNaN(ms) ? COUNT_MS : ms, ease: el.dataset.countEase || "slow" };
}

/**
 * Counts ``el`` up to ``count`` when it comes into view, over ``ms`` milliseconds along the ``ease`` curve (at once
 * with ms 0 or without motion). ``format`` writes a value (the Reviews total: "416+"); ``decimals``: the values'
 * decimals. Returns a cleanup function.
 */
export function countUp(el, count, { ms = COUNT_MS, ease = "slow", decimals = 0, format = null } = {}) {
    if (!el) {
        return () => {};
    }
    const target = count || 0;
    const show = (n) => (el.textContent = format ? format(n) : `${n.toLocaleString()}+`);
    const round = (n) => Number(n.toFixed(decimals));
    if (!target) {
        el.textContent = format ? format(0) : "";
        return () => {};
    }
    if (!ms || window.matchMedia("(prefers-reduced-motion: reduce)").matches || !window.IntersectionObserver) {
        show(target);
        return () => {};
    }
    show(0);
    let frame;
    const observer = new IntersectionObserver((entries) => {
        if (!entries[0].isIntersecting) {
            return;
        }
        observer.disconnect();
        const start = performance.now();
        const step = (now) => {
            const t = Math.min(1, (now - start) / ms);
            show(t >= 1 ? target : round(target * (EASINGS[ease] || EASINGS.slow)(t)));
            if (t < 1) {
                frame = requestAnimationFrame(step);
            }
        };
        frame = requestAnimationFrame(step);
    }, { threshold: 0.4 });
    observer.observe(el);
    return () => {
        observer.disconnect();
        cancelAnimationFrame(frame);
    };
}

/** A counting number's text (the Counter block): its prefix, ``value`` with its decimals, its suffix. */
export function counterText(el, value) {
    const d = el.dataset;
    const decimals = Math.max(0, Math.min(4, parseInt(d.mtbgCountDecimals) || 0));
    const number = Number(value).toLocaleString(document.documentElement.lang || undefined, {
        minimumFractionDigits: decimals, maximumFractionDigits: decimals,
    });
    return `${d.mtbgCountPrefix || ""}${number}${d.mtbgCountSuffix || ""}`;
}

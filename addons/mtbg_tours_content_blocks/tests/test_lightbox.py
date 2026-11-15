from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'mtbg')
class TestSharedLightbox(HttpCase):
    """The shared photo viewer's opt-ins (0.11.4): a Download button and video slides only when a page asks for them;
    without them it is as before (no Download, photos only)."""

    def test_opt_ins(self):
        code = """
        (async () => {
            const check = (ok, what) => { if (!ok) { throw new Error('viewer: ' + what); } };
            const wait = (ms) => new Promise((r) => setTimeout(r, ms));
            for (let i = 0; i < 100 && !window.odoo?.loader?.modules.get('@mtbg_tours_content_blocks/shared/lightbox'); i++) { await wait(100); }
            const lb = odoo.loader.modules.get('@mtbg_tours_content_blocks/shared/lightbox');
            const photo = (n) => ({src: '/web/static/img/placeholder.png', width: 800, height: 600, alt: 'p' + n});
            // as before: no Download
            let pswp = await lb.openLightbox([photo(1), photo(2)], 0);
            await wait(400);
            check(!document.querySelector('.pswp .mtbg-pswp-download'), 'no Download without the option');
            check(document.querySelector('.pswp__counter'), 'the counter');
            pswp.close(); await wait(600);
            // opted in: Download (on slides with a downloadUrl) and a video slide
            const clicked = [];
            pswp = await lb.openLightbox(
                [Object.assign(photo(1), {downloadUrl: '/x/1'}), lb.videoSlide({src: '/x/v.mp4', width: 1080, height: 1920, downloadUrl: '/x/2'}), photo(3)],
                0, {download: {label: 'Download', onClick: (slide) => clicked.push(slide.downloadUrl)}});
            await wait(400);
            const dl = document.querySelector('.pswp .mtbg-pswp-download');
            check(dl && !dl.hidden, 'Download shown');
            dl.click();
            check(clicked.join() === '/x/1', 'Download hands over the slide');
            pswp.next(); await wait(400);
            const video = pswp.currSlide.container.querySelector('video.mtbg-pswp-video[controls][playsinline]');
            check(video && video.style.aspectRatio.replace(/\\s/g, '') === '1080/1920', 'a video slide at its shape');
            pswp.next(); await wait(300);
            check(dl.hidden, 'no Download for a slide without one');
            pswp.close();
            console.log('test successful');
        })().catch((error) => console.error(error.message));
        """
        self.browser_js('/web/login', code, "true", timeout=120)

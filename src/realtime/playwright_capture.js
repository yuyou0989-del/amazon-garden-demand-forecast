async (page) => {
  // 仅一次导航；不改身份、登录状态、代理或浏览器指纹。
  const initialURL = 'https://www.amazon.com/s?k=garden+hose';
  const crawlTime = new Date().toISOString();
  const network = [];
  const pending = [];
  const warnings = [];
  const onResponse = (response) => {
    const request = response.request();
    const entry = {url: request.url(), method: request.method(),
      resource_type: request.resourceType(), status: response.status(),
      content_type: response.headers()['content-type'] || null,
      contains_product_data: null, session_cookie_present: null,
      authorization_header_present: null};
    network.push(entry);
    pending.push((async () => {
      const headers = await request.allHeaders();
      entry.session_cookie_present = Boolean(headers.cookie);
      entry.authorization_header_present = Boolean(headers.authorization);
      if (['xhr', 'fetch'].includes(entry.resource_type)) {
        const declared = Number(response.headers()['content-length']);
        if (declared > 2097152) {entry.body_inspection = 'skipped_large_response'; return;}
        const body = await response.body();
        entry.response_bytes = body.length;
        entry.body_inspection = body.length <= 2097152 ? 'structural_marker_check' : 'skipped_large_response';
        if (body.length <= 2097152) {
          const text = body.toString('utf8');
          entry.contains_product_data = /data-component-type=["']s-search-result/.test(text)
            || (/"asin"\s*:/.test(text) && /"(?:title|price)"\s*:/.test(text));
        }
      }
    })().catch(e => {entry.inspection_error = String(e);}));
  };
  const failed = [];
  const onFailed = request => failed.push({url: request.url(), method: request.method(),
    resource_type: request.resourceType(), error: request.failure()?.errorText || null});
  page.on('response', onResponse);
  page.on('requestfailed', onFailed);
  let response = null, navigationError = null, domLoaded = false, original = null;
  try {
    response = await page.goto(initialURL, {waitUntil: 'domcontentloaded', timeout: 45000});
    domLoaded = true;
  } catch (error) {navigationError = String(error);}
  if (response) {
    try {original = await response.body();} catch (error) {warnings.push('initial_body: ' + String(error));}
  }
  let html = '', title = null, screenshot = null;
  try {html = await page.content(); title = await page.title();} catch (error) {warnings.push('dom: ' + String(error));}
  // 只有正常页面才等待其既有加载完成，不刷新或发起额外接口请求。
  const blocked = response && (response.status() < 200 || response.status() >= 300);
  if (!blocked && !navigationError && !/robot check|validateCaptcha|enter the characters you see below/i.test(html)) {
    try {await page.waitForLoadState('load', {timeout: 10000}); html = await page.content();}
    catch (error) {warnings.push('load_wait: ' + String(error));}
  }
  try {screenshot = await page.screenshot({timeout: 10000});} catch (error) {warnings.push('screenshot: ' + String(error));}
  await Promise.allSettled(pending);
  page.removeListener('response', onResponse);
  page.removeListener('requestfailed', onFailed);
  const redirects = [];
  let previous = response?.request().redirectedFrom();
  while (previous) {const r = await previous.response(); redirects.unshift({url: previous.url(), status: r?.status() || null}); previous = previous.redirectedFrom();}
  return {crawl_time: crawlTime, keyword: 'garden hose', collection_method: 'playwright',
    request_method: 'GET', initial_url: initialURL, final_url: page.url(),
    status_code: response?.status() || null, content_type: response?.headers()['content-type'] || null,
    page_title: title, dom_loaded: domLoaded, navigation_error: navigationError,
    redirects, redirected: redirects.length > 0 || page.url() !== initialURL,
    top_level_navigation_attempts: 1, browser: 'system Google Chrome, headed; isolated default context',
    html, initial_html_base64: original?.toString('base64') || null,
    screenshot_base64: screenshot?.toString('base64') || null,
    network, failed_requests: failed, warnings, end_time: new Date().toISOString()};
}

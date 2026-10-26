import {test, expect} from '@playwright/test';

test.beforeEach(async ({page})=>{
  await page.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/auth/status')return route.fulfill({json:{setup_required:false}});
    return route.fulfill({status:path==='/api/local-recovery'?403:401,json:{detail:path==='/api/local-recovery'?'Direct password reset is available only in the local desktop app.':'Synthetic signed-out fixture.'}});
  });
});

for(const width of [320,390,1440]){
  test(`sign-in identity, reading order and keyboard flow at ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:900});
    await page.goto('/');
    await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible();
    await expect(page.locator('.login-brand-name')).toHaveText('Aegis');
    await expect(page.locator('.login-brand-tagline')).toBeVisible();
    const metrics=await page.evaluate(()=>{
      const card=document.querySelector('.login-card')!,story=document.querySelector('.login-story')!,tagline=document.querySelector('.login-brand-tagline')!;
      return {taskFirst:Boolean(card.compareDocumentPosition(story)&Node.DOCUMENT_POSITION_FOLLOWING),width:document.documentElement.scrollWidth,viewport:window.innerWidth,card:card.getBoundingClientRect().top,story:story.getBoundingClientRect().top,font:parseFloat(getComputedStyle(tagline).fontSize)};
    });
    expect(metrics.taskFirst).toBe(true);
    expect(metrics.width).toBeLessThanOrEqual(metrics.viewport);
    expect(metrics.font).toBeGreaterThanOrEqual(14);
    if(width<761)expect(metrics.card).toBeLessThan(metrics.story);
    const username=page.getByLabel('Username',{exact:true}),password=page.getByLabel('Password',{exact:true});
    await expect(username).toHaveAttribute('autocomplete','username');
    await expect(password).toHaveAttribute('autocomplete','current-password');
    await username.focus();await page.keyboard.press('Tab');await expect(password).toBeFocused();
    expect(await password.evaluate(el=>parseFloat(getComputedStyle(el).outlineWidth))).toBeGreaterThanOrEqual(2);
    await page.keyboard.press('Tab');await expect(page.getByRole('button',{name:'Show password',exact:true})).toBeFocused();
    await page.keyboard.press('Enter');await expect(password).toHaveAttribute('type','text');
    await page.keyboard.press('Enter');await expect(password).toHaveAttribute('type','password');
    await page.screenshot({path:`../output/playwright/sprint1/sign-in-${width}.png`,fullPage:true});
    await username.fill('');
    await page.getByRole('button',{name:'Sign in',exact:true}).click();
    await expect(username).toBeFocused();
    await expect(page.getByText('Enter your username.',{exact:true})).toBeVisible();
  });
}

test('reflow, artwork failure, reduced motion and repeated recovery navigation preserve sign-in',async({page})=>{
  await page.setViewportSize({width:320,height:900});
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.route('**/_next/image*',route=>route.abort());
  await page.goto('/');
  await expect(page.locator('.login-brand-tagline')).toBeVisible();
  await page.evaluate(()=>document.documentElement.style.fontSize='200%');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await expect(page.getByRole('button',{name:'Sign in',exact:true})).toBeVisible();
  await page.evaluate(()=>document.documentElement.style.fontSize='');
  for(let i=0;i<2;i++){
    await page.getByRole('link',{name:'Forgot password?'}).click();
    await expect(page.getByRole('heading',{name:'Recover your access'})).toBeFocused();
    await expect(page.getByRole('button',{name:'Reset password',exact:true})).toHaveCount(0);
    await page.getByRole('link',{name:'Back to sign in'}).click();
    await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible();
  }
});

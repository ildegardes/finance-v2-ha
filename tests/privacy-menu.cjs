async function selectPrivacy(page,mode){
  const toggle=page.locator('#money-privacy-toggle');
  await toggle.click();
  const chosen=page.locator('[data-privacy-mode="'+mode+'"]');
  if(await chosen.count())await chosen.click();
}

async function togglePrivacy(page){
  const mode=await page.locator('html').getAttribute('data-money-privacy');
  await selectPrivacy(page,mode==='visible'?'full':'visible');
}

module.exports={selectPrivacy,togglePrivacy};

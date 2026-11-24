const fs=require('fs'),path=require('path'),{execFileSync}=require('child_process');
const root=path.resolve(__dirname,'..');
for(let i=0;i<3;i++){
 const config=require('./theme-'+i+'.json');
 config.content=[path.join(root,'src/phishguard/web/static/**/*.html'),path.join(root,'src/phishguard/web/static/assets/app.js')];
 const generated=path.join(__dirname,'.generated-'+i+'.cjs');
 fs.writeFileSync(generated,'module.exports='+JSON.stringify(config)+';module.exports.plugins=[require("@tailwindcss/forms"),require("@tailwindcss/container-queries")];');
 try{execFileSync(process.execPath,[require.resolve('tailwindcss/lib/cli.js'),'-c',generated,'-i',path.join(__dirname,'input.css'),'-o',path.join(root,`src/phishguard/web/static/assets/theme-${i}.css`),'--minify'],{stdio:'inherit'});}finally{fs.unlinkSync(generated);}
}

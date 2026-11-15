import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const runtime=createRequire(path.join(process.argv[2],'package.json'));
const {Workbook,SpreadsheetFile,FileBlob}=await import(pathToFileURL(runtime.resolve('@oai/artifact-tool')).href);
for(const [file,sheet,range] of [['finance-july.xlsx','TongHop','A1:D26'],['custom.xlsx','BangTinh','A1:D8']]){
 const book=await SpreadsheetFile.importXlsx(await FileBlob.load('.test-tmp/office-qa/'+file));book.recalculate();
 const s=book.worksheets.getItem(sheet);
 if(sheet==='TongHop')console.log(JSON.stringify({file,revenue:s.getRange('B9').values,profit:s.getRange('B20').values}));
 else console.log(JSON.stringify({file,total:s.getRange('D4').values}));
 const rendered=await book.render({sheetName:sheet,range,scale:1.5,format:'png'});await fs.writeFile('.test-tmp/office-qa/'+file+'.png',new Uint8Array(await rendered.arrayBuffer()));
}

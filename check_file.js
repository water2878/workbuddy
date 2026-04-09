const fs = require('fs');
try {
  const s = fs.statSync('C:/Users/Lenovo/Desktop/cervical_health.gif');
  console.log('文件大小:', s.size, 'bytes');
} catch(e) {
  console.log('文件不存在:', e.message);
}

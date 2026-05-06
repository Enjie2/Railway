#!/bin/sh

# 下载并解压核心执行文件 (以 sing-box 为例)
wget -O - https://github.com/SagerNet/sing-box/releases/download/v1.8.5/sing-box-1.8.5-linux-amd64.tar.gz | tar xz
cp sing-box-*/sing-box ./ && rm -rf sing-box-*

# 生成配置文件，直接引用你在 Render 设置的环境变量
cat << EOF > config.json
{
  "inbounds": [{
    "type": "vless",
    "listen": "::",
    "listen_port": ${PORT},
    "users": [{"uuid": "${UUID}"}],
    "transport": {"type": "ws", "path": "${WSPATH}"}
  }],
  "outbounds": [{"type": "direct"}]
}
EOF

# 启动服务
./sing-box run -c config.json
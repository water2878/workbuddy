$params = '{"page_size":20}'
& npx -y @larksuite/cli api GET /open-apis/im/v1/chats --params $params --as user 2>&1

$params = '{"container_id_type":"chat_id","container_id":"oc_0170529c7f11a6faa43785a6910d4cf1","page_size":20}'
& npx -y @larksuite/cli api GET /open-apis/im/v1/messages --params $params --as user 2>&1

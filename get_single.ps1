$params = '{"container_id_type":"open_id","container_id":"ou_4a86846caf437e8fda2fc9f2794c5424","page_size":20}'
& npx -y @larksuite/cli api GET /open-apis/im/v1/messages --params $params --as user 2>&1

from datetime import datetime
from flask import render_template, request
from pypdf import PdfReader
from io import BytesIO
import os
import re
from qcloud_cos import CosConfig
from qcloud_cos import CosS3Client
from run import app
from wxcloudrun.dao import delete_counterbyid, query_counterbyid, insert_counter, update_counterbyid
from wxcloudrun.model import Counters
from wxcloudrun.response import make_succ_empty_response, make_succ_response, make_err_response


@app.route('/')
def index():
    """
    :return: 返回index页面
    """
    return render_template('index.html')


@app.route('/api/count', methods=['POST'])
def count():
    """
    :return:计数结果/清除结果
    """

    # 获取请求体参数
    params = request.get_json()

    # 检查action参数
    if 'action' not in params:
        return make_err_response('缺少action参数')

    # 按照不同的action的值，进行不同的操作
    action = params['action']

    # 执行自增操作
    if action == 'inc':
        counter = query_counterbyid(1)
        if counter is None:
            counter = Counters()
            counter.id = 1
            counter.count = 1
            counter.created_at = datetime.now()
            counter.updated_at = datetime.now()
            insert_counter(counter)
        else:
            counter.id = 1
            counter.count += 1
            counter.updated_at = datetime.now()
            update_counterbyid(counter)
        return make_succ_response(counter.count)

    # 执行清0操作
    elif action == 'clear':
        delete_counterbyid(1)
        return make_succ_empty_response()

    # action参数错误
    else:
        return make_err_response('action参数错误')


@app.route('/api/count', methods=['GET'])
def get_count():
    """
    :return: 计数的值
    """
    counter = Counters.query.filter(Counters.id == 1).first()
    return make_succ_response(0) if counter is None else make_succ_response(counter.count)


@app.route('/api/pdf/parse', methods=['POST'])
def parse_pdf():
    """
    从腾讯云存储下载PDF文件并解析
    使用fileID从云存储下载文件，fileID格式: cloud://envId.bucket/文件路径
    :return: PDF解析后的文本内容
    """
    # 获取请求体参数
    params = request.get_json()
    
    # 检查fileID参数
    if not params or 'fileID' not in params:
        return make_err_response('缺少fileID参数')
    
    file_id = params['fileID']
    
    # 验证fileID格式 (cloud://envId.bucket/文件路径)
    if not file_id.startswith('cloud://'):
        return make_err_response('fileID格式错误，应以cloud://开头')
    
    try:
        # 解析fileID: cloud://envId.bucket/文件路径
        # 例如: cloud://prod-7ge7496129e8b09c.7072-prod-7ge7496129e8b09c-1312737058/files/xxx.pdf
        match = re.match(r'cloud://([^.]+)\.([^/]+)/(.+)', file_id)
        if not match:
            return make_err_response('fileID格式错误')
        
        env_id, bucket, file_path = match.groups()
        
        # 检查文件类型
        if not file_path.lower().endswith('.pdf'):
            return make_err_response('文件类型错误，不是PDF文件')
        
        # 从环境变量获取腾讯云密钥（云托管环境会自动注入）
        secret_id = os.environ.get('TENCENTCLOUD_SECRETID')
        secret_key = os.environ.get('TENCENTCLOUD_SECRETKEY')
        
        if not secret_id or not secret_key:
            return make_err_response('缺少腾讯云密钥配置')
        
        # 配置COS客户端
        # 微信云存储通常使用上海地域
        region = 'ap-shanghai'
        config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)
        client = CosS3Client(config)
        
        # 从COS下载文件
        response = client.get_object(
            Bucket=bucket,
            Key=file_path
        )
        
        # 读取文件内容
        pdf_content = response['Body'].get_raw_stream().read()
        
        # 将内容转换为BytesIO对象供PdfReader使用
        pdf_data = BytesIO(pdf_content)
        
        # 使用PdfReader解析PDF
        pdf_reader = PdfReader(pdf_data)
        
        # 提取所有页面的文本
        text_content = []
        for page in pdf_reader.pages:
            text = page.extract_text()
            if text:
                text_content.append(text)
        
        # 合并所有页面的文本
        full_text = '\n\n'.join(text_content)
        
        return make_succ_response({
            'text': full_text,
            'page_count': len(pdf_reader.pages)
        })
    
    except Exception as e:
        return make_err_response(f'PDF解析失败: {str(e)}')

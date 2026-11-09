import { useEffect, useState } from 'react'
import {
  Button, Card, Col, Descriptions, Form, Input, InputNumber, Modal, Pagination, Row,
  Space, Table, Tag, Typography, message,
} from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { useNavigate, useParams } from 'react-router-dom'
import http, { fmtMoney, fmtTime } from '../../api/client'

const TX_TYPE = { recharge: ['充值', 'success'], adjust: ['调整', 'warning'], consumption: ['消费', 'error'], refund: ['退款', 'default'] }

export default function TenantDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [tenant, setTenant] = useState(null)
  const [tx, setTx] = useState({ items: [], total: 0, page: 1, pageSize: 20 })
  const [txLoading, setTxLoading] = useState(false)
  const [userOpen, setUserOpen] = useState(false)
  const [userForm] = Form.useForm()

  const load = () => http.get(`/api/admin/tenants/${id}`).then(setTenant)
  const loadTx = async (page = 1) => {
    setTxLoading(true)
    try {
      const r = await http.get(`/api/admin/tenants/${id}/transactions`, { params: { page, page_size: tx.pageSize } })
      setTx({ ...r, page, pageSize: tx.pageSize })
    } finally {
      setTxLoading(false)
    }
  }

  useEffect(() => {
    load()
    loadTx()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const resetPwd = (row) => {
    let value = ''
    Modal.confirm({
      title: `为「${row.username}」设置新密码`,
      content: <Input.Password onChange={(e) => (value = e.target.value)} placeholder="至少 6 位" />,
      onOk: async () => {
        if (!value || value.length < 6) {
          message.error('密码至少 6 位')
          throw new Error()
        }
        await http.post(`/api/admin/tenants/${id}/users/${row.id}`, { password: value })
        message.success('已重置')
      },
    })
  }

  const quickRecharge = () => {
    let value = ''
    Modal.confirm({
      title: '充值',
      content: <InputNumber onChange={(v) => (value = v)} style={{ width: 200 }} prefix="¥" min={0.01} precision={2} />,
      onOk: async () => {
        if (!value) throw new Error()
        await http.post(`/api/admin/tenants/${id}/recharge`, { amount: value, note: '管理员充值' })
        message.success('充值成功')
        load()
      },
    })
  }

  const txColumns = [
    { title: '时间', dataIndex: 'created_at', width: 160, render: fmtTime },
    {
      title: '类型', dataIndex: 'type', width: 90,
      render: (t) => <Tag color={TX_TYPE[t]?.[1]}>{TX_TYPE[t]?.[0] || t}</Tag>,
    },
    {
      title: '金额', dataIndex: 'amount', width: 130,
      render: (v) => (
        <Typography.Text type={v >= 0 ? 'success' : 'danger'} strong>
          {v >= 0 ? '+' : ''}{fmtMoney(v, 4)}
        </Typography.Text>
      ),
    },
    { title: '余额', dataIndex: 'balance_after', width: 110, render: (v) => fmtMoney(v, 4) },
    { title: '备注', dataIndex: 'note' },
    { title: '操作者', dataIndex: 'operator', width: 100 },
  ]

  return (
    tenant && (
      <div>
        <Space style={{ marginBottom: 16 }}>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/admin/tenants')}>
            返回租户列表
          </Button>
          <Typography.Title level={4} style={{ margin: 0 }}>
            租户：{tenant.name} <Typography.Text type="secondary">{tenant.code}</Typography.Text>
          </Typography.Title>
        </Space>
        <Row gutter={[16, 16]}>
          <Col span={8}>
            <Card title="钱包">
              <Typography.Title level={2} type={tenant.balance <= 0 ? 'danger' : 'success'} style={{ margin: 0 }}>
                ¥{fmtMoney(tenant.balance, 4)}
              </Typography.Title>
              <Descriptions column={1} size="small" style={{ marginTop: 16 }}>
                <Descriptions.Item label="状态">
                  <Tag color={tenant.status === 'active' ? 'success' : 'default'}>
                    {tenant.status === 'active' ? '正常' : '停用'}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="封锁">{tenant.blocked ? `是（${tenant.blocked_reason}）` : '否'}</Descriptions.Item>
                <Descriptions.Item label="欠费阈值">{fmtMoney(tenant.low_balance_threshold, 2)}</Descriptions.Item>
                <Descriptions.Item label="联系人">{tenant.contact_name || '-'} {tenant.contact_phone}</Descriptions.Item>
                <Descriptions.Item label="创建时间">{fmtTime(tenant.created_at)}</Descriptions.Item>
              </Descriptions>
            </Card>
            <Card title="门户账号" style={{ marginTop: 16 }}>
              <Table
                size="small"
                rowKey="id"
                pagination={false}
                dataSource={tenant.users || []}
                columns={[
                  { title: '用户名', dataIndex: 'username' },
                  {
                    title: '状态', dataIndex: 'status', width: 70,
                    render: (s) => <Tag color={s === 'active' ? 'success' : 'default'}>{s === 'active' ? '正常' : '停用'}</Tag>,
                  },
                  {
                    title: '操作', width: 150,
                    render: (_, r) => (
                      <Space>
                        <Button size="small" onClick={() => resetPwd(r)}>重置密码</Button>
                        <Button
                          size="small"
                          danger={r.status === 'active'}
                          onClick={async () => {
                            await http.post(`/api/admin/tenants/${id}/users/${r.id}`, { status: r.status === 'active' ? 'disabled' : 'active' })
                            load()
                          }}
                        >
                          {r.status === 'active' ? '停用' : '启用'}
                        </Button>
                      </Space>
                    ),
                  },
                ]}
              />
              <Button type="primary" size="small" style={{ marginTop: 8 }} onClick={() => setUserOpen(true)}>
                新建门户账号
              </Button>
            </Card>
          </Col>
          <Col span={16}>
            <Card title="钱包流水">
              <Table
                rowKey="id"
                size="small"
                loading={txLoading}
                columns={txColumns}
                dataSource={tx.items}
                pagination={false}
              />
              <Pagination
                style={{ marginTop: 8, textAlign: 'right' }}
                current={tx.page}
                pageSize={tx.pageSize}
                total={tx.total}
                onChange={loadTx}
                showTotal={(t) => `共 ${t} 条`}
                size="small"
              />
            </Card>
            <Card title="快捷操作" style={{ marginTop: 16 }}>
              <Space>
                <Button type="primary" onClick={quickRecharge}>充值</Button>
                <Button onClick={() => navigate(`/admin/usage?tenant_id=${id}`)}>查看用量流水</Button>
                <Button onClick={() => navigate(`/admin/sessions?tenant_id=${id}`)}>查看会话</Button>
              </Space>
            </Card>
          </Col>
        </Row>

        <Modal
          title="新建门户账号"
          open={userOpen}
          onCancel={() => setUserOpen(false)}
          onOk={async () => {
            const v = await userForm.validateFields()
            await http.post(`/api/admin/tenants/${id}/users`, v)
            message.success('已创建')
            setUserOpen(false)
            userForm.resetFields()
            load()
          }}
          destroyOnHidden
        >
          <Form form={userForm} layout="vertical">
            <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="password" label="密码" rules={[{ required: true, min: 6 }]}>
              <Input.Password />
            </Form.Item>
            <Form.Item name="display_name" label="显示名">
              <Input />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    )
  )
}

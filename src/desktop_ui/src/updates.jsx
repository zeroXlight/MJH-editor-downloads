import React, {useState} from 'react';
import {Button, Modal, Progress, Radio, Space} from 'antd';

export function Updates({state, mobileEnabled}) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const messages = {
    idle: '可以手动检查更新。',
    checking: '正在检查 GitHub 上的正式版本…',
    current: '当前已是最新版。',
    available: state.latest ? '发现新版 V' + state.latest + '。' : '有可用更新。',
    downloading: state.transfer === 'patching'
      ? '差分包已下载，正在重建和校验安装包…'
      : `正在下载${state.transfer === 'delta' ? '差分包' : '完整安装包'}，可以继续使用编辑器。`,
    ready: '安装包已验证，正常退出编辑器后安装。',
  };
  const busy = ['checking', 'downloading'].includes(state.status);
  const badge = state.status === 'ready' ? '更新待安装' : state.status === 'available' ? '有新版本' : '更新与资源';
  const percent = state.total ? Math.floor(100 * state.received / state.total) : 0;
  const size = bytes => (bytes / 1048576).toFixed(1) + ' MB';

  async function act(action, mode) {
    setError('');
    try {
      await window.pywebview.api.update(action, mode);
    } catch (err) {
      setError(String(err));
    }
  }

  return <>
    <Button size="small" type={['available', 'ready'].includes(state.status) ? 'primary' : 'default'} onClick={() => setOpen(true)}>{badge}</Button>
    <Modal title="更新与资源" open={open} footer={<Button onClick={() => setOpen(false)}>关闭</Button>} onCancel={() => setOpen(false)}>
      <p>当前版本 V{state.current} · 手游资源{mobileEnabled ? '已安装' : '未安装'}</p>
      <Radio.Group
        aria-label="更新方式"
        value={state.mode}
        onChange={event => act('mode', event.target.value)}
        options={[
          {label: '发现新版时提醒', value: 'notify'},
          {label: '自动下载，退出后安装', value: 'auto', disabled: !state.managed},
        ]}
      />
      {!state.managed && <p>通过安装器安装后可启用自动安装。</p>}
      <p role="status">{error || state.message || messages[state.status]}</p>
      {state.status === 'downloading' && state.total > 0 && <div>
        <Progress percent={percent} status={percent < 100 ? 'active' : 'normal'} aria-label="更新下载进度"/>
        <p>{size(state.received)} / {size(state.total)}</p>
      </div>}
      <Space wrap>
        <Button disabled={busy || state.pending} onClick={() => act('check')}>检查新版</Button>
        {state.status === 'available' &&
          <Button type="primary" onClick={() => act('download')}>{state.managed ? '下载并在退出后安装' : '打开新版下载页'}</Button>}
        {(state.pending || state.status === 'downloading') && <Button onClick={() => act('cancel')}>取消本次安装</Button>}
      </Space>
      <p>补装可选组件时，重新运行当前版本的安装器，选择同一安装目录。</p>
      <p>编辑器无法启动时，可在 Windows 开始菜单打开「MJH-editor 更新与修复」。</p>
      <Space wrap>
        <Button onClick={() => act('components')}>当前版本安装器</Button>
        <Button onClick={() => act('source')}>下载当前版本源码</Button>
      </Space>
    </Modal>
  </>;
}

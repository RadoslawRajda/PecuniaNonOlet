import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import WebView, {type WebViewMessageEvent} from 'react-native-webview';
import {TURNSTILE_SITE_KEY} from '@env';
import {COLORS, createThemedStyles} from '../theme';

type CaptchaMessage = {type?: string; token?: string; height?: number};

export function TurnstileCaptcha({
  onToken,
  resetKey,
}: {
  onToken: (token: string) => void;
  resetKey: number;
}) {
  const [height, setHeight] = React.useState(76);
  const webView = React.useRef<WebView<{}>>(null);

  React.useEffect(() => {
    if (resetKey > 0) {
      onToken('');
      webView.current?.injectJavaScript(
        "if (window.turnstile && window.widgetId !== null) { window.turnstile.reset(window.widgetId); } true;",
      );
    }
  }, [resetKey, onToken]);

  if (!TURNSTILE_SITE_KEY) {
    return (
      <View style={styles.missing}>
        <Text style={styles.message}>Weryfikacja CAPTCHA nie jest skonfigurowana.</Text>
      </View>
    );
  }

  const siteKey = JSON.stringify(TURNSTILE_SITE_KEY);
  const html = `<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1"><style>
    html,body{margin:0;padding:0;background:transparent;color:#a1a1aa;font:14px -apple-system,BlinkMacSystemFont,sans-serif;overflow:hidden}
    #widget{width:100%;min-height:65px;display:flex;align-items:center;justify-content:center}
  </style></head><body><div id="widget"></div><script>
    window.widgetId=null;
    const send=(data)=>window.ReactNativeWebView.postMessage(JSON.stringify(data));
    const resize=()=>send({type:'height',height:Math.max(70,Math.min(document.body.scrollHeight,320))});
    new ResizeObserver(resize).observe(document.body);
    function mount(){if(!window.turnstile||window.widgetId!==null)return;window.widgetId=window.turnstile.render('#widget',{
      sitekey:${siteKey},theme:'dark',size:'flexible',action:'register',
      callback:(token)=>send({type:'success',token}),
      'expired-callback':()=>send({type:'expired'}),
      'error-callback':()=>send({type:'error'})
    });resize();}
    window.addEventListener('load',mount);
    const loader=document.createElement('script');loader.src='https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';loader.async=true;loader.defer=true;loader.onload=mount;loader.onerror=()=>send({type:'error'});document.head.appendChild(loader);
  </script></body></html>`;

  return (
    <View style={styles.container}>
      <Text style={styles.label}>Weryfikacja</Text>
      <WebView
        ref={webView}
        source={{html, baseUrl: 'https://pecunianonolet.local'}}
        originWhitelist={['*']}
        javaScriptEnabled
        domStorageEnabled
        scrollEnabled={false}
        bounces={false}
        style={[styles.webview, {height}]}
        onMessage={(event: WebViewMessageEvent) => {
          try {
            const message = JSON.parse(event.nativeEvent.data) as CaptchaMessage;
            if (message.type === 'success' && message.token) onToken(message.token);
            else if (message.type === 'expired' || message.type === 'error') onToken('');
            else if (message.type === 'height' && typeof message.height === 'number') {
              setHeight(Math.max(70, Math.min(message.height, 320)));
            }
          } catch {
            onToken('');
          }
        }}
        onError={() => onToken('')}
      />
      <Text style={styles.hint}>Potwierdź weryfikację, aby utworzyć konto.</Text>
    </View>
  );
}

const styles = createThemedStyles(() => StyleSheet.create({
  container: {gap: 5},
  label: {color: COLORS.muted, fontSize: 14, fontWeight: '500'},
  webview: {width: '100%', alignSelf: 'stretch', backgroundColor: 'transparent'},
  hint: {color: COLORS.muted, fontSize: 12},
  missing: {minHeight: 58, justifyContent: 'center'},
  message: {color: COLORS.muted, fontSize: 13},
}));

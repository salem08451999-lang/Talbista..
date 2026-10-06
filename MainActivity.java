package ly.talbista.app;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.ContentResolver;
import android.media.AudioAttributes;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        createChannels();
        super.onCreate(savedInstanceState);
    }

    private void channel(NotificationManager nm, String id, String name, String sound, long[] vibration) {
        NotificationChannel c = new NotificationChannel(id, name, NotificationManager.IMPORTANCE_HIGH);
        if (sound != null) {
            AudioAttributes aa = new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build();
            c.setSound(Uri.parse(ContentResolver.SCHEME_ANDROID_RESOURCE + "://" + getPackageName() + "/raw/" + sound), aa);
        }
        c.enableVibration(true);
        c.setVibrationPattern(vibration);
        c.enableLights(true);
        nm.createNotificationChannel(c);
    }

    private void createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        // Channel settings are fixed once created on a device; change the id to change sound/vibration later.
        channel(nm, "talbista_urgent", "طلبات مستعجلة", "talbista_urgent", new long[]{0, 500, 150, 500, 150, 500, 150, 900});
        channel(nm, "talbista_offer", "طلبات جديدة", "talbista_offer", new long[]{0, 250, 120, 250});
        channel(nm, "talbista_default", "إشعارات طلبيستا", null, new long[]{0, 200});
    }
}

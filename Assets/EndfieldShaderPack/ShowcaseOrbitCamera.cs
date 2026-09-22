using UnityEngine;

namespace EndfieldShaderPack
{
    /// <summary>
    /// 展示用轨道相机：右键拖动环绕、滚轮缩放、T 键自动旋转、R 键重置。
    /// 挂到 Main Camera 上，target 拖角色根节点即可。
    /// </summary>
    public class ShowcaseOrbitCamera : MonoBehaviour
    {
        public Transform target;
        public float distance = 3.0f;
        public float minDistance = 0.8f;
        public float maxDistance = 10f;
        public float orbitSpeed = 120f;   // deg per full drag
        public float zoomSpeed = 1.5f;
        public float pitchMin = -5f;
        public float pitchMax = 85f;
        public float targetHeight = 1.0f; // 注视点在角色局部的高度（米）
        public bool autoRotate = false;
        public float autoRotateSpeed = 30f;

        float _yaw = 180f;   // 从角色正面看（角色面朝 +Z，相机在 -Z 方向）
        float _pitch = 8f;

        void Start()
        {
            if (target == null) AutoFindTarget();
            ResetView();
        }

        void AutoFindTarget()
        {
            var root = GameObject.Find("chr_0034_typhoea_rebuilt");
            if (root != null) target = root.transform;
        }

        void ResetView()
        {
            _yaw = 180f; _pitch = 8f;
            distance = Mathf.Clamp(distance, minDistance, maxDistance);
            UpdatePose();
        }

        void Update()
        {
            if (target == null) AutoFindTarget();
            if (target == null) return;

            // 右键环绕
            if (Input.GetMouseButton(1))
            {
                _yaw += Input.GetAxis("Mouse X") * orbitSpeed * Time.deltaTime;
                _pitch -= Input.GetAxis("Mouse Y") * orbitSpeed * Time.deltaTime;
                _pitch = Mathf.Clamp(_pitch, pitchMin, pitchMax);
            }

            // 滚轮缩放
            float scroll = Input.GetAxis("Mouse ScrollWheel");
            if (Mathf.Abs(scroll) > 1e-4f)
                distance = Mathf.Clamp(distance * (1f - scroll * zoomSpeed), minDistance, maxDistance);

            // T 切换自动旋转，R 重置
            if (Input.GetKeyDown(KeyCode.T)) autoRotate = !autoRotate;
            if (Input.GetKeyDown(KeyCode.R)) ResetView();
            if (autoRotate) _yaw += autoRotateSpeed * Time.deltaTime;

            UpdatePose();
        }

        void UpdatePose()
        {
            Vector3 focus = target.position + Vector3.up * targetHeight;
            Quaternion rot = Quaternion.Euler(_pitch, _yaw, 0f);
            transform.position = focus + rot * new Vector3(0f, 0f, -distance);
            transform.rotation = Quaternion.LookRotation(focus - transform.position, Vector3.up);
        }
    }
}

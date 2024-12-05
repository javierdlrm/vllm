@Library("jenkins-library@main")

import com.logicalclocks.jenkins.k8s.ImageBuilder

properties([
  parameters([
    choice(name: 'branch', choices: ['', 'v0.6.4-4.1'],  description: 'Which branch to build'),
  ])
])

node("local") {
    stage('Clone repository') {
      if (params.branch == ''){
        checkout scm
      } else {
        sshagent (credentials: ['id_rsa']) {
          sh """
            git fetch --all
            git checkout ${params.branch}
            git pull
          """
        }
      }
    }

    stage('Build and push image(s)') {
        version = readFile "${env.WORKSPACE}/VERSION"
        withEnv(["VERSION=${version.trim()}"]) {
          
            def builder = new ImageBuilder(this)
            m = readFile "${env.WORKSPACE}/build-manifest.json"
            builder.run(m)
        }
    }
}